import matplotlib
matplotlib.use('Agg')
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from reportador.models import Cliente, ClienteCorreo, Inspeccion, InspeccionDetalle, InspeccionEvidencia, PDFInspeccion
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Avg, Case, When, Value, IntegerField
from django.db.models.functions import ExtractWeekDay, TruncMonth
import json
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from weasyprint import HTML
import matplotlib.pyplot as plt
import traceback
from django.conf import settings
import traceback
import io
import base64
from django.core.mail import EmailMessage
from .models import ConsolidadoCliente, PDFConsolidado
from usuarios.decorators import usuarios_en_grupos
from django.utils.decorators import method_decorator
from pypdf import PdfWriter, PdfReader
from django.core.files.base import ContentFile
from datetime import datetime


@method_decorator(usuarios_en_grupos(['admin_roka']), name='dispatch')
class DashboardIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'admin_roka/form_cliente.html'

@login_required
@usuarios_en_grupos(['admin_roka'])
def guardar_cliente(request):
    # Si la petición es un GET normal, renderiza la plantilla limpia
    if request.method == 'GET':
        return render(request, 'admin_roka/form_cliente.html')
        
    if request.method == 'POST':
        # 1. Recuperar campos del formulario
        nombre = request.POST.get('nombre', '').strip()
        nit = request.POST.get('nit', '').strip()
        administrador = request.POST.get('administrador', '').strip()
        lista_correos = request.POST.getlist('correos[]')

        # 2. Validaciones básicas (Retornando JSON en lugar de render)
        if not nombre or not nit:
            return JsonResponse({
                'status': 'error',
                'message': 'El nombre y el NIT son campos obligatorios.'
            }, status=400)

        if Cliente.objects.filter(nit=nit).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'Ya existe un cliente registrado con el NIT {nit}.'
            }, status=400)

        try:
            # 3. Guardar el objeto Cliente principal
            nuevo_cliente = Cliente.objects.create(
                nombre=nombre,
                nit=nit,
                administrador=administrador
            )

            # 4. Procesar y guardar cada correo asociado
            for correo in lista_correos:
                correo_limpio = correo.strip()
                if correo_limpio:
                    ClienteCorreo.objects.create(
                        cliente=nuevo_cliente,
                        correo=correo_limpio
                    )

            # Respuesta de Éxito Limpia en JSON para el JavaScript
            return JsonResponse({
                'status': 'success',
                'message': f"Cliente '{nombre}' registrado con éxito de manera correcta."
            }, status=201)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f"Ocurrió un error inesperado al guardar: {str(e)}"
            }, status=500)
            
    # Por si llega algún método no soportado en este endpoint
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)


VALOR_NUM_CASE = Case(
    When(calificacion="Excelente", then=Value(5)),
    When(calificacion="Regular", then=Value(3)),
    When(calificacion="Mala", then=Value(1)),
    output_field=IntegerField(),
)
 
ORDEN_CALIFICACION = ["Excelente", "Regular", "Mala"]
MAPEO_DIAS = {2: "Lunes", 3: "Martes", 4: "Miércoles", 5: "Jueves", 6: "Viernes", 7: "Sábado", 1: "Domingo"}


@login_required
@usuarios_en_grupos(['admin_roka'])
def dashboard_analytics(request):
    # -----------------------------------------------------------------
    # 1. Frecuencia de informes por día de la semana
    # -----------------------------------------------------------------
    dias_data = (
        Inspeccion.objects.annotate(dia_semana=ExtractWeekDay("fecha"))
        .values("dia_semana")
        .annotate(total=Count("id"))
        .order_by("dia_semana")
    )
    cronograma_informes = {dia: 0 for dia in MAPEO_DIAS.values()}
    for d in dias_data:
        nombre_dia = MAPEO_DIAS.get(d["dia_semana"])
        if nombre_dia:
            cronograma_informes[nombre_dia] = d["total"]

    # -----------------------------------------------------------------
    # 2. Calificación promedio por cliente (TODOS LOS CLIENTES)
    # -----------------------------------------------------------------
    clientes_calificacion_qs = (
        InspeccionDetalle.objects.annotate(valor_num=VALOR_NUM_CASE)
        .values("inspeccion__cliente__nombre")
        .annotate(promedio=Avg("valor_num"), total_revisiones=Count("id"))
        .order_by("-promedio", "-total_revisiones")
    )

    ranking_clientes = [
        {
            "inspeccion__cliente__nombre": c["inspeccion__cliente__nombre"],
            "promedio": round(c["promedio"], 2),
            "total_revisiones": c["total_revisiones"]
        }
        for c in clientes_calificacion_qs
    ]

    mejor_cliente = ranking_clientes[0] if ranking_clientes else None
    
    # Para el peor cliente, buscamos preferencia entre quienes tienen >1 revisión
    peor_cliente = None
    if ranking_clientes:
        candidatos_peores = [c for c in ranking_clientes if c["total_revisiones"] >= 2]
        peor_cliente = candidatos_peores[-1] if candidatos_peores else ranking_clientes[-1]

    # -----------------------------------------------------------------
    # 3. Zonas / conceptos técnicos
    # -----------------------------------------------------------------
    zonas_inspeccionadas = (
        InspeccionDetalle.objects.values("concepto")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # -----------------------------------------------------------------
    # 4. Distribución de enfoques
    # -----------------------------------------------------------------
    enfoques_distribucion = (
        InspeccionDetalle.objects.values("enfoque")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # -----------------------------------------------------------------
    # 5. Distribución global de calificaciones
    # -----------------------------------------------------------------
    distribucion_raw = (
        InspeccionDetalle.objects.values("calificacion")
        .annotate(total=Count("id"))
    )
    mapa_calificacion = {d["calificacion"]: d["total"] for d in distribucion_raw}
    valores_calificacion = [mapa_calificacion.get(c, 0) for c in ORDEN_CALIFICACION]

    # -----------------------------------------------------------------
    # 6. Evolución mensual del volumen de inspecciones
    # -----------------------------------------------------------------
    evolucion_mensual = (
        Inspeccion.objects.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    labels_meses = [e["mes"].strftime("%b %Y") for e in evolucion_mensual if e["mes"]]
    valores_meses = [e["total"] for e in evolucion_mensual if e["mes"]]

    # -----------------------------------------------------------------
    # 7. KPIs generales
    # -----------------------------------------------------------------
    promedio_general = (
        InspeccionDetalle.objects.annotate(valor_num=VALOR_NUM_CASE)
        .aggregate(prom=Avg("valor_num"))["prom"]
        or 0
    )
    total_inspecciones = Inspeccion.objects.count()
    total_evidencias = InspeccionEvidencia.objects.count()
    total_clientes_evaluados = len(ranking_clientes)

    angulo_gauge = round(-90 + (float(promedio_general) / 5 * 180), 1)

    # -----------------------------------------------------------------
    # Contexto enviando la TOTALIDAD de los clientes
    # -----------------------------------------------------------------
    context = {
        "labels_dias": json.dumps(list(cronograma_informes.keys())),
        "valores_dias": json.dumps(list(cronograma_informes.values())),

        # Enviamos la totalidad de los clientes serializados a JS
        "labels_clientes": json.dumps(
            [c["inspeccion__cliente__nombre"] for c in ranking_clientes]
        ),
        "valores_clientes": json.dumps([c["promedio"] for c in ranking_clientes]),

        "labels_zonas": json.dumps([z["concepto"] or "Sin especificar" for z in zonas_inspeccionadas]),
        "valores_zonas": json.dumps([z["total"] for z in zonas_inspeccionadas]),

        "labels_enfoques": json.dumps([e["enfoque"] or "Sin especificar" for e in enfoques_distribucion]),
        "valores_enfoques": json.dumps([e["total"] for e in enfoques_distribucion]),

        "labels_calificacion": json.dumps(ORDEN_CALIFICACION),
        "valores_calificacion": json.dumps(valores_calificacion),

        "labels_meses": json.dumps(labels_meses),
        "valores_meses": json.dumps(valores_meses),

        # KPIs
        "promedio_general": round(promedio_general, 2),
        "angulo_gauge": angulo_gauge,
        "total_inspecciones": total_inspecciones,
        "total_evidencias": total_evidencias,
        "total_clientes_evaluados": total_clientes_evaluados,
        "mejor_cliente": mejor_cliente,
        "peor_cliente": peor_cliente,
        
        # AQUÍ SE MANDA EL LISTADO COMPLETO DE CLIENTES (SIN CORTAR)
        "ranking_clientes": ranking_clientes,
    }

    return render(request, "admin_roka/dashboard_admin.html", context)
 
 
def calcular_metricas_consolidado(cliente, fecha_inicio, fecha_fin):
    """
    Cálculo consolidado acotado por cliente y rango de fechas.
    """
    inspecciones_qs = Inspeccion.objects.filter(
        cliente=cliente, fecha__gte=fecha_inicio, fecha__lte=fecha_fin
    ).order_by('fecha', 'hora')

    detalles_qs = InspeccionDetalle.objects.filter(inspeccion__in=inspecciones_qs)

    promedio_general = (
        detalles_qs.annotate(valor_num=VALOR_NUM_CASE).aggregate(prom=Avg('valor_num'))['prom']
        or 0
    )

    zonas = detalles_qs.values('concepto').annotate(total=Count('id')).order_by('-total')
    enfoques = detalles_qs.values('enfoque').annotate(total=Count('id')).order_by('-total')

    distribucion_raw = detalles_qs.values('calificacion').annotate(total=Count('id'))
    mapa_calificacion = {d['calificacion']: d['total'] for d in distribucion_raw}
    valores_calificacion = [mapa_calificacion.get(c, 0) for c in ORDEN_CALIFICACION]

    evolucion = (
        inspecciones_qs.annotate(mes=TruncMonth('fecha'))
        .values('mes').annotate(total=Count('id')).order_by('mes')
    )

    total_evidencias = InspeccionEvidencia.objects.filter(
        detalle__inspeccion__in=inspecciones_qs
    ).count()

    return {
        'inspecciones': inspecciones_qs,
        'promedio_general': round(promedio_general, 2),
        'angulo_gauge': round(-90 + (float(promedio_general) / 5 * 180), 1),
        'total_inspecciones': inspecciones_qs.count(),
        'total_evidencias': total_evidencias,
        'labels_zonas': [z['concepto'] or 'Sin especificar' for z in zonas],
        'valores_zonas': [z['total'] for z in zonas],
        'labels_enfoques': [e['enfoque'] or 'Sin especificar' for e in enfoques],
        'valores_enfoques': [e['total'] for e in enfoques],
        'labels_calificacion': ORDEN_CALIFICACION,
        'valores_calificacion': valores_calificacion,
        'labels_meses': [e['mes'].strftime('%b %Y') for e in evolucion if e['mes']],
        'valores_meses': [e['total'] for e in evolucion if e['mes']],
    }
 
 

def generar_grafico_barras(labels, valores, color='#0b57a3', horizontal=False, figsize=(6, 3)):
   
    if not labels or not valores:
        return None

    plt.close('all')
    fig, ax = plt.subplots(figsize=figsize, dpi=150)

    if horizontal:
        bars = ax.barh(labels, valores, color=color, height=0.6)
        ax.invert_yaxis()
        ax.bar_label(bars, padding=3, fontsize=7, color='#334155')
    else:
        bars = ax.bar(labels, valores, color=color, width=0.5)
        ax.bar_label(bars, padding=3, fontsize=7, color='#334155')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cbd5e1')
    ax.spines['bottom'].set_color('#cbd5e1')
    ax.tick_params(labelsize=8, colors='#475569')

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    return f"data:image/png;base64,{base64.b64encode(buf.read()).decode('utf-8')}"
 
 
# ---------------------------------------------------------------------------
# 1. Página del selector (cliente + rango de fechas)
# ---------------------------------------------------------------------------
@login_required
@usuarios_en_grupos(['admin_roka'])
def consolidado_selector(request):
    clientes = Cliente.objects.all().order_by('nombre')
    return render(request, 'admin_roka/consolidado_form.html', {'clientes': clientes})
 
 
# ---------------------------------------------------------------------------
# 2. Preview AJAX: listado de inspecciones + datos para las gráficas
# ---------------------------------------------------------------------------
@login_required
@usuarios_en_grupos(['admin_roka'])
def api_consolidado_preview(request):
    cliente_id = request.GET.get('cliente_id')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
 
    if not (cliente_id and fecha_inicio and fecha_fin):
        return JsonResponse(
            {"status": "error", "message": "Debe seleccionar un cliente y un rango de fechas."},
            status=400
        )
 
    cliente = get_object_or_404(Cliente, id=cliente_id)
    metricas = calcular_metricas_consolidado(cliente, fecha_inicio, fecha_fin)
 
    inspecciones_data = [
        {
            "id": i.id,
            "fecha": i.fecha.strftime('%d/%m/%Y'),
            "hora": i.hora.strftime('%H:%M') if i.hora else '',
            "administrador": i.administrador,
            "total_bloques": i.detalles.count(),
        }
        for i in metricas['inspecciones']
    ]
 
    return JsonResponse({
        "status": "success",
        "cliente_nombre": cliente.nombre,
        "inspecciones": inspecciones_data,
        "total_inspecciones": metricas['total_inspecciones'],
        "total_evidencias": metricas['total_evidencias'],
        "promedio_general": metricas['promedio_general'],
        "angulo_gauge": metricas['angulo_gauge'],
        "labels_zonas": metricas['labels_zonas'],
        "valores_zonas": metricas['valores_zonas'],
        "labels_enfoques": metricas['labels_enfoques'],
        "valores_enfoques": metricas['valores_enfoques'],
        "labels_calificacion": metricas['labels_calificacion'],
        "valores_calificacion": metricas['valores_calificacion'],
        "labels_meses": metricas['labels_meses'],
        "valores_meses": metricas['valores_meses'],
    })
 
 
# ---------------------------------------------------------------------------
# 3. Generar el consolidado: guarda el registro, arma el PDF y envía el correo
# ---------------------------------------------------------------------------
@login_required
@usuarios_en_grupos(['admin_roka'])
def generar_consolidado(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Método no permitido."}, status=405)

    try:
        cliente_id = request.POST.get('cliente_id')
        fecha_inicio_raw = request.POST.get('fecha_inicio')
        fecha_fin_raw = request.POST.get('fecha_fin')
        conclusion_general = request.POST.get('conclusion_general', '').strip()

        if not (cliente_id and fecha_inicio_raw and fecha_fin_raw):
            return JsonResponse(
                {"status": "error", "message": "Faltan datos del cliente o del rango de fechas."},
                status=400
            )

        # Convertimos los textos en objetos date reales
        fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d').date()

        cliente = get_object_or_404(Cliente, id=cliente_id)
        metricas = calcular_metricas_consolidado(cliente, fecha_inicio, fecha_fin)
        inspecciones_qs = metricas['inspecciones']

        if not inspecciones_qs.exists():
            return JsonResponse({
                "status": "error",
                "message": "No hay inspecciones registradas para este cliente en el rango seleccionado."
            }, status=400)

        # --- 1. Registro del Consolidado en Base de Datos ---
        consolidado = ConsolidadoCliente.objects.create(
            cliente=cliente,
            fecha_inicio=fecha_inicio, # Pasa como objeto date
            fecha_fin=fecha_fin,       # Pasa como objeto date
            conclusion_general=conclusion_general,
            administrador=request.user,
        )
        consolidado.inspecciones.set(inspecciones_qs)

        # --- 2. Generar la carátula/resumen ejecutiva con WeasyPrint ---
        grafico_calificacion = generar_grafico_barras(
            metricas['labels_calificacion'], metricas['valores_calificacion'],
            color=['#01A684', '#f59e0b', '#ef4444'] # Colores corporativos ROKA
        )
        grafico_zonas = generar_grafico_barras(
            metricas['labels_zonas'], metricas['valores_zonas'],
            color='#0b57a3', horizontal=True
        )

        logo_url = request.build_absolute_uri(f"{settings.STATIC_URL}img/Roka_Logo_azul_pdf.png")

        contexto_pdf = {
            "logo_url": logo_url,
            "cliente_nombre": cliente.nombre,
            "cliente_nit": cliente.nit,
            "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d'),
            "fecha_fin": fecha_fin.strftime('%Y-%m-%d'),
            "total_inspecciones": metricas['total_inspecciones'],
            "total_evidencias": metricas['total_evidencias'],
            "promedio_general": metricas['promedio_general'],
            "conclusion_general": conclusion_general,
            "grafico_calificacion": grafico_calificacion,
            "grafico_zonas": grafico_zonas,
        }

        html_string = render_to_string('admin_roka/pdf_consolidado.html', contexto_pdf)
        portada_bytes = HTML(
            string=html_string, base_url=request.build_absolute_uri('/')
        ).write_pdf()

        # --- 3. Fusión de PDFs con PyPDF ---
        merger = PdfWriter()
        merger.append(io.BytesIO(portada_bytes))

        pdfs_inspecciones = PDFInspeccion.objects.filter(inspeccion__in=inspecciones_qs)
        
        for pdf_obj in pdfs_inspecciones:
            if pdf_obj.archivo:
                try:
                    pdf_bytes = pdf_obj.archivo.read()
                    merger.append(io.BytesIO(pdf_bytes))
                except Exception as err_file:
                    print(f"Error al leer el PDF de la inspección {pdf_obj.inspeccion_id}: {err_file}")

        pdf_final_buffer = io.BytesIO()
        merger.write(pdf_final_buffer)
        merger.close()
        pdf_final_bytes = pdf_final_buffer.getvalue()

        # --- 4. Guardar en Cloudflare R2 usando PDFConsolidado ---
        nombre_archivo_pdf = f"consolidado_{cliente.nit}_{fecha_inicio}_a_{fecha_fin}.pdf"
        
        pdf_consolidado_obj = PDFConsolidado.objects.create(
            consolidado=consolidado,
            enviado=False
        )
        pdf_consolidado_obj.archivo.save(
            nombre_archivo_pdf,
            ContentFile(pdf_final_bytes),
            save=True
        )

        # --- 5. Envío del Correo electrónico ---
        lista_correos = [
            str(c).strip() for c in cliente.correos_contacto.values_list('correo', flat=True) if c
        ]
        if not lista_correos:
            lista_correos = [str(settings.EMAIL_HOST_USER).strip()]

        asunto = f"Consolidado de Inspecciones - {cliente.nombre} ({fecha_inicio} a {fecha_fin})"
        cuerpo_correo = "\n".join([
            "Cordial saludo,",
            "",
            f"Adjunto encontrará el informe consolidado de las inspecciones técnicas realizadas a {cliente.nombre} "
            f"entre el {fecha_inicio} y el {fecha_fin}.",
            "",
            f"Total de inspecciones incluidas: {metricas['total_inspecciones']}",
            f"Calificación promedio general: {metricas['promedio_general']} / 5",
            "",
            "Conclusión general:",
            conclusion_general or "Sin observaciones adicionales.",
            "",
            "Quedamos atentos ante cualquier inquietud sobre el contenido de este informe.",
            "",
            "Atentamente,",
            "Roka Servicios Integrales",
        ])

        email = EmailMessage(
            subject=asunto,
            body=cuerpo_correo,
            from_email=str(settings.DEFAULT_FROM_EMAIL),
            to=lista_correos,
        )

        nombre_pdf_adjunto = f"Consolidado_{cliente.nombre.replace(' ', '_')}_{fecha_inicio}_a_{fecha_fin}.pdf"
        email.attach(nombre_pdf_adjunto, pdf_final_bytes, 'application/pdf')
        email.send(fail_silently=False)

        pdf_consolidado_obj.enviado = True
        pdf_consolidado_obj.save(update_fields=['enviado'])

        return JsonResponse({
            "status": "success",
            "message": f"Consolidado generado y enviado correctamente a: {', '.join(lista_correos)}",
            "consolidado_id": consolidado.id,
        }, status=201)

    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"status": "error", "message": f"Error en el proceso: {str(e)}"}, status=500)