import matplotlib
matplotlib.use('Agg')
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from reportador.models import Cliente, ClienteCorreo
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Avg, Case, When, Value, IntegerField
from django.db.models.functions import ExtractWeekDay, TruncMonth
from reportador.models import Inspeccion, InspeccionDetalle, InspeccionEvidencia
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
from .models import ConsolidadoCliente
from usuarios.decorators import usuarios_en_grupos
from django.utils.decorators import method_decorator


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
    mapeo_dias = {2: "Lunes", 3: "Martes", 4: "Miércoles", 5: "Jueves",
                  6: "Viernes", 7: "Sábado", 1: "Domingo"}
    cronograma_informes = {dia: 0 for dia in mapeo_dias.values()}
    for d in dias_data:
        nombre_dia = mapeo_dias.get(d["dia_semana"])
        if nombre_dia:
            cronograma_informes[nombre_dia] = d["total"]
 
    # -----------------------------------------------------------------
    # 2. Calificación promedio por cliente (Excelente=5, Regular=3, Mala=1)
    #    Se trae el listado completo para poder construir tanto el chart
    #    (top 10) como el ranking / KPIs de mejor-peor cliente.
    # -----------------------------------------------------------------
    valor_num_case = Case(
        When(calificacion="Excelente", then=Value(5)),
        When(calificacion="Regular", then=Value(3)),
        When(calificacion="Mala", then=Value(1)),
        output_field=IntegerField(),
    )
 
    clientes_calificacion = list(
        InspeccionDetalle.objects.annotate(valor_num=valor_num_case)
        .values("inspeccion__cliente__nombre")
        .annotate(promedio=Avg("valor_num"), total_revisiones=Count("id"))
        .order_by("-promedio")
    )
    for c in clientes_calificacion:
        c["promedio"] = round(c["promedio"], 2)
 
    ranking_clientes = clientes_calificacion  # ya viene ordenado desc
    mejor_cliente = ranking_clientes[0] if ranking_clientes else None
    peor_cliente = ranking_clientes[-1] if ranking_clientes else None
    top10_clientes = ranking_clientes[:10]
 
    # -----------------------------------------------------------------
    # 3. Zonas / conceptos técnicos más inspeccionados
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
    # 5. NUEVO: distribución global de calificaciones (Excelente/Regular/Mala)
    # -----------------------------------------------------------------
    orden_calificacion = ["Excelente", "Regular", "Mala"]
    distribucion_raw = (
        InspeccionDetalle.objects.values("calificacion")
        .annotate(total=Count("id"))
    )
    mapa_calificacion = {d["calificacion"]: d["total"] for d in distribucion_raw}
    valores_calificacion = [mapa_calificacion.get(c, 0) for c in orden_calificacion]
 
    # -----------------------------------------------------------------
    # 6. NUEVO: evolución mensual del volumen de inspecciones
    # -----------------------------------------------------------------
    evolucion_mensual = (
        Inspeccion.objects.annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    labels_meses = [e["mes"].strftime("%b %Y") for e in evolucion_mensual]
    valores_meses = [e["total"] for e in evolucion_mensual]
 
    # -----------------------------------------------------------------
    # 7. NUEVO: KPIs generales + ángulo para el gauge de calidad
    # -----------------------------------------------------------------
    promedio_general = (
        InspeccionDetalle.objects.annotate(valor_num=valor_num_case)
        .aggregate(prom=Avg("valor_num"))["prom"]
        or 0
    )
    total_inspecciones = Inspeccion.objects.count()
    total_evidencias = InspeccionEvidencia.objects.count()
    total_clientes_evaluados = len(ranking_clientes)
 
    # El gauge es un semicírculo de -90° a 90° sobre una escala de 0 a 5
    angulo_gauge = round(-90 + (float(promedio_general) / 5 * 180), 1)
 
    # -----------------------------------------------------------------
    # Todo lo que va a JS se serializa con json.dumps: evita romper la
    # sintaxis si un nombre de cliente/concepto trae comillas, tildes
    # dentro de comillas, etc. (a diferencia de volcar str(list) con |safe)
    # -----------------------------------------------------------------
    context = {
        "labels_dias": json.dumps(list(cronograma_informes.keys())),
        "valores_dias": json.dumps(list(cronograma_informes.values())),
 
        "labels_clientes": json.dumps(
            [c["inspeccion__cliente__nombre"] for c in top10_clientes]
        ),
        "valores_clientes": json.dumps([c["promedio"] for c in top10_clientes]),
 
        "labels_zonas": json.dumps([z["concepto"] for z in zonas_inspeccionadas]),
        "valores_zonas": json.dumps([z["total"] for z in zonas_inspeccionadas]),
 
        "labels_enfoques": json.dumps([e["enfoque"] for e in enfoques_distribucion]),
        "valores_enfoques": json.dumps([e["total"] for e in enfoques_distribucion]),
 
        "labels_calificacion": json.dumps(orden_calificacion),
        "valores_calificacion": json.dumps(valores_calificacion),
 
        "labels_meses": json.dumps(labels_meses),
        "valores_meses": json.dumps(valores_meses),
 
        # KPIs / gauge / ranking (estos se usan directo en el template, no en JS)
        "promedio_general": round(promedio_general, 2),
        "angulo_gauge": angulo_gauge,
        "total_inspecciones": total_inspecciones,
        "total_evidencias": total_evidencias,
        "total_clientes_evaluados": total_clientes_evaluados,
        "mejor_cliente": mejor_cliente,
        "peor_cliente": peor_cliente,
        "ranking_clientes": ranking_clientes[:8],
    }
 
    return render(request, "admin_roka/dashboard_admin.html", context)


VALOR_NUM_CASE = Case(
    When(calificacion="Excelente", then=Value(5)),
    When(calificacion="Regular", then=Value(3)),
    When(calificacion="Mala", then=Value(1)),
    output_field=IntegerField(),
)
 
ORDEN_CALIFICACION = ["Excelente", "Regular", "Mala"]
 
 
def calcular_metricas_consolidado(cliente, fecha_inicio, fecha_fin):
    """
    Misma lógica de agregación del dashboard general, pero acotada a un
    cliente y un rango de fechas puntual. Se reutiliza tanto para el preview
    AJAX en pantalla como para los datos que alimentan el PDF del consolidado.
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
        'labels_zonas': [z['concepto'] for z in zonas],
        'valores_zonas': [z['total'] for z in zonas],
        'labels_enfoques': [e['enfoque'] for e in enfoques],
        'valores_enfoques': [e['total'] for e in enfoques],
        'labels_calificacion': ORDEN_CALIFICACION,
        'valores_calificacion': valores_calificacion,
        'labels_meses': [e['mes'].strftime('%b %Y') for e in evolucion],
        'valores_meses': [e['total'] for e in evolucion],
    }
 
 

def generar_grafico_barras(labels, valores, color='#1f7ca5', horizontal=False, figsize=(6, 3)):
    """
    Genera una gráfica de barras como PNG en base64 para incrustar en el PDF.
    WeasyPrint no ejecuta JavaScript, así que Chart.js no sirve aquí: las
    gráficas del consolidado se generan del lado del servidor con matplotlib.
    Requiere `pip install matplotlib`.
    """
    if not labels:
        return None
 
    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    if horizontal:
        ax.barh(labels, valores, color=color)
        ax.invert_yaxis()
    else:
        ax.bar(labels, valores, color=color)
 
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cbd5e1')
    ax.spines['bottom'].set_color('#cbd5e1')
    ax.tick_params(labelsize=8, colors='#475569')
    fig.tight_layout()
 
    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True)
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
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        conclusion_general = request.POST.get('conclusion_general', '').strip()
 
        if not (cliente_id and fecha_inicio and fecha_fin):
            return JsonResponse(
                {"status": "error", "message": "Faltan datos del cliente o del rango de fechas."},
                status=400
            )
 
        cliente = get_object_or_404(Cliente, id=cliente_id)
        metricas = calcular_metricas_consolidado(cliente, fecha_inicio, fecha_fin)
        inspecciones_qs = metricas['inspecciones'].prefetch_related('detalles__evidencias')
 
        if not inspecciones_qs.exists():
            return JsonResponse({
                "status": "error",
                "message": "No hay inspecciones registradas para este cliente en el rango seleccionado."
            }, status=400)
 
        # --- 1. Registro del consolidado ---
        consolidado = ConsolidadoCliente.objects.create(
            cliente=cliente,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            conclusion_general=conclusion_general,
            administrador=request.user,
        )
        consolidado.inspecciones.set(inspecciones_qs)
 
        # --- 2. Datos por inspección para el PDF (todas las evidencias incluidas) ---
        inspecciones_pdf = []
        for insp in inspecciones_qs:
            detalles_pdf = []
            for index, det in enumerate(insp.detalles.all()):
                imagenes_urls = [
                    request.build_absolute_uri(ev.archivo.url)
                    for ev in det.evidencias.all() if ev.archivo
                ]
                detalles_pdf.append({
                    "numero": index + 1,
                    "enfoque": det.enfoque,
                    "concepto": det.concepto,
                    "calificacion": det.calificacion,
                    "observacion": det.observacion or "",
                    "imagenes": imagenes_urls,
                })
            inspecciones_pdf.append({
                "id": insp.id,
                "fecha": str(insp.fecha),
                "hora": insp.hora.strftime('%H:%M') if insp.hora else '',
                "administrador": insp.administrador,
                "supervisor": insp.supervisor,
                "conclusion": insp.conclusion or "",
                "detalles": detalles_pdf,
            })
 
        # --- 3. Gráficas resumen incrustadas (server-side, WeasyPrint no corre JS) ---
        grafico_calificacion = generar_grafico_barras(
            metricas['labels_calificacion'], metricas['valores_calificacion'],
            color=['#10b981', '#f59e0b', '#ef4444']
        )
        grafico_zonas = generar_grafico_barras(
            metricas['labels_zonas'], metricas['valores_zonas'],
            color='#1f7ca5', horizontal=True
        )
 
        logo_url = request.build_absolute_uri(f"{settings.STATIC_URL}img/Roka_Logo_azul_pdf.png")
 
        contexto_pdf = {
            "logo_url": logo_url,
            "cliente_nombre": cliente.nombre,
            "cliente_nit": cliente.nit,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "total_inspecciones": metricas['total_inspecciones'],
            "total_evidencias": metricas['total_evidencias'],
            "promedio_general": metricas['promedio_general'],
            "conclusion_general": conclusion_general,
            "grafico_calificacion": grafico_calificacion,
            "grafico_zonas": grafico_zonas,
            "inspecciones": inspecciones_pdf,
        }
 
        html_string = render_to_string('admin_roka/pdf_consolidado.html', contexto_pdf)
        pdf_bytes = HTML(
            string=html_string, base_url=request.build_absolute_uri('/')
        ).write_pdf()
 
        # --- 4. Correo a TODOS los contactos registrados del cliente ---
        lista_correos = [
            str(c).strip() for c in cliente.correos_contacto.values_list('correo', flat=True) if c
        ]
        if not lista_correos:
            lista_correos = [str(settings.EMAIL_HOST_USER).strip()]
 
        asunto = f"Consolidado de Inspecciones - {cliente.nombre} ({fecha_inicio} a {fecha_fin})"
        cuerpo_correo = "\n".join([
            "Cordial saludo,",
            "",
            f"Adjunto encontrará el consolidado de inspecciones técnicas realizadas a {cliente.nombre} "
            f"entre el {fecha_inicio} y el {fecha_fin}.",
            "",
            f"Total de inspecciones en el período: {metricas['total_inspecciones']}",
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
        nombre_pdf = f"Consolidado_{cliente.nombre.replace(' ', '_')}_{fecha_inicio}_a_{fecha_fin}.pdf"
        email.attach(nombre_pdf, pdf_bytes, 'application/pdf')
        email.send(fail_silently=False)
 
        return JsonResponse({
            "status": "success",
            "message": f"Consolidado generado y enviado correctamente a: {', '.join(lista_correos)}",
            "consolidado_id": consolidado.id,
        }, status=201)
 
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({"status": "error", "message": f"Error en el proceso: {str(e)}"}, status=500)