from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Cliente, InspeccionDetalle, InspeccionEvidencia, Inspeccion, PDFInspeccion
from django.db.models import Q
from django.db import transaction
import io
from django.db import transaction
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from weasyprint import HTML
import os
import traceback
from django.contrib.staticfiles import finders
import json
import language_tool_python
from django.views.decorators.csrf import csrf_exempt
from usuarios.decorators import usuarios_en_grupos
from django.utils.decorators import method_decorator
from datetime import datetime
from django.core.files.base import ContentFile



@method_decorator(usuarios_en_grupos(['reportador_roka']), name='dispatch')
class DashboardIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'reportador/form.html'
    

@login_required
@usuarios_en_grupos(['reportador_roka', 'admin_roka'])
def api_buscar_clientes(request):
    term = request.GET.get('q', '').strip()

    # Optimizamos la consulta usando prefetch_related para traer los correos eficientemente de un solo golpe
    if term:
        clientes = Cliente.objects.filter(
            Q(nombre__icontains=term) | Q(nit__icontains=term)
        ).prefetch_related('correos_contacto')[:20]
    else:
        clientes = Cliente.objects.all().prefetch_related('correos_contacto')[:20]

    data = []
    for c in clientes:
        # Extraemos todos los valores del campo 'correo' asociados a este cliente en una lista plana ['correo1@...', 'correo2@...']
        lista_correos = list(c.correos_contacto.values_list('correo', flat=True))
        
        data.append({
            'id': c.id,
            'nombre': c.nombre,
            'nit': c.nit,
            'administrador': c.administrador or '',
            'correos': lista_correos,  # <--- Ahora sí enviamos la lista real al JavaScript
        })

    return JsonResponse(data, safe=False)




def link_callback(uri, rel):
    """
    Convierte URLs de STATIC y MEDIA en rutas físicas para xhtml2pdf.
    """

    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(
            settings.MEDIA_ROOT,
            uri.replace(settings.MEDIA_URL, "")
        )

    elif uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, ""))

        if not path:
            raise Exception(f"No se encontró el archivo estático: {uri}")

    else:
        return uri

    if not os.path.isfile(path):
        raise Exception(f"No existe el archivo: {path}")

    return path



@login_required
@usuarios_en_grupos(['reportador_roka'])
def guardar_inspeccion(request):
    if request.method == "POST":
        inspeccion_id = None
        try:
            # 1. Bloque de Base de Datos (Transacción Atómica)
            with transaction.atomic():
                cliente_id = request.POST.get('cliente_id')
                if not cliente_id:
                    return JsonResponse({"status": "error", "message": "No se seleccionó un cliente válido."}, status=400)

                cliente = Cliente.objects.get(id=cliente_id)

                # --- Conversión segura de fecha y hora a objetos de Python ---
                fecha_raw = request.POST.get('fecha')
                if not fecha_raw:
                    return JsonResponse({"status": "error", "message": "La fecha es requerida."}, status=400)
                
                try:
                    fecha_obj = datetime.strptime(fecha_raw.strip(), '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({"status": "error", "message": "Formato de fecha inválido. Debe ser YYYY-MM-DD."}, status=400)

                hora_raw = request.POST.get('hora')
                hora_obj = None
                if hora_raw and hora_raw.strip():
                    try:
                        formato_hora = '%H:%M:%S' if len(hora_raw.strip()) == 8 else '%H:%M'
                        hora_obj = datetime.strptime(hora_raw.strip(), formato_hora).time()
                    except ValueError:
                        return JsonResponse({"status": "error", "message": "Formato de hora inválido."}, status=400)

                inspeccion = Inspeccion.objects.create(
                    cliente=cliente,
                    usuario=request.user,
                    fecha=fecha_obj,
                    hora=hora_obj,
                    administrador=request.POST.get('administrador'),
                    supervisor=request.POST.get('supervisor', 'Nicolas Gaviria Gonzalez'),
                    correo=request.POST.get('correo'),
                    conclusion=request.POST.get('conclusion')
                )

                inspeccion_id = inspeccion.id

                # Extraer listas limpias tolerando variaciones de nombre
                enfoques = request.POST.getlist('enfoque[]') or request.POST.getlist('enfoque')
                conceptos = request.POST.getlist('concepto[]') or request.POST.getlist('concepto')
                calificaciones = request.POST.getlist('calificacion[]') or request.POST.getlist('calificacion')
                observaciones = request.POST.getlist('observacion[]') or request.POST.getlist('observacion')

                total_evaluaciones = int(request.POST.get('total_evaluaciones', 0))

                if total_evaluaciones == 0:
                    total_evaluaciones = max(len(enfoques), len(conceptos), 1)

                for i in range(total_evaluaciones):
                    enf_val = enfoques[i] if i < len(enfoques) else ''
                    con_val = conceptos[i] if i < len(conceptos) else ''
                    cal_val = calificaciones[i] if i < len(calificaciones) else 'Regular'
                    obs_val = observaciones[i] if i < len(observaciones) else ''

                    if not enf_val and not con_val and cal_val == 'Regular' and not obs_val:
                        continue

                    detalle = InspeccionDetalle.objects.create(
                        inspeccion=inspeccion,
                        enfoque=str(enf_val),
                        concepto=str(con_val),
                        calificacion=str(cal_val),
                        observacion=str(obs_val)
                    )

                    archivos = request.FILES.getlist(f'evidencias_{i}')
                    for archivo in archivos:
                        InspeccionEvidencia.objects.create(detalle=detalle, archivo=archivo)

            # 2. Flujo Posterior: PDF y Correo (Fuera de la transacción)
            inspeccion_creada = Inspeccion.objects.prefetch_related('detalles__evidencias').get(id=inspeccion_id)
            cliente_obj = inspeccion_creada.cliente

            query_correos = cliente_obj.correos_contacto.values_list('correo', flat=True)
            lista_correos = [str(correo).strip() for correo in query_correos if correo]

            if not lista_correos:
                lista_correos = [str(settings.EMAIL_HOST_USER).strip()]

            detalles_pdf = []

            for index, det in enumerate(inspeccion_creada.detalles.all()):
                imagenes_urls = [
                    request.build_absolute_uri(ev.archivo.url)
                    for ev in det.evidencias.all()
                    if ev.archivo
                ]

                detalles_pdf.append({
                    "numero": index + 1,
                    "enfoque": det.enfoque,
                    "concepto": det.concepto,
                    "calificacion": det.calificacion,
                    "observacion": det.observacion or "",
                    "imagenes": imagenes_urls,
                })

            logo_url = request.build_absolute_uri(f"{settings.STATIC_URL}img/Roka_Logo_azul_pdf.png")

            datos_plano_pdf = {
                "logo_url": logo_url,
                'cliente_nombre': str(cliente_obj.nombre),
                'cliente_nit': str(cliente_obj.nit),
                'fecha': str(inspeccion_creada.fecha.strftime('%Y-%m-%d') if hasattr(inspeccion_creada.fecha, 'strftime') else inspeccion_creada.fecha),
                'hora': str(inspeccion_creada.hora.strftime('%H:%M') if inspeccion_creada.hora and hasattr(inspeccion_creada.hora, 'strftime') else ''),
                'administrador': str(inspeccion_creada.administrador or 'No asignado'),
                'supervisor': str(inspeccion_creada.supervisor),
                'conclusion': str(inspeccion_creada.conclusion or ''),
                'detalles': detalles_pdf
            }

            html_string = render_to_string('reportador/pdf_inspeccion.html', datos_plano_pdf)

            # --- Generación del PDF con WeasyPrint ---
            pdf_bytes = HTML(
                string=html_string,
                base_url=request.build_absolute_uri('/')
            ).write_pdf()
            
            # --- GUARDAR PDF EN CLOUDFLARE Y EN BASE DE DATOS ---
            nombre_archivo_pdf = f"{inspeccion_creada.fecha}_inspeccion_{inspeccion_creada.id}.pdf"
            
            pdf_registro, _ = PDFInspeccion.objects.get_or_create(
                inspeccion=inspeccion_creada
            )
            # Al asignar mediante save(), Django pasa el archivo al storage de Cloudflare
            pdf_registro.archivo.save(
                nombre_archivo_pdf,
                ContentFile(pdf_bytes),
                save=False
            )
            pdf_registro.enviado = False
            pdf_registro.save()

            # 3. Envío del Correo
            asunto = f"Informe de Inspección Técnica - {cliente_obj.nombre} ({inspeccion_creada.fecha})"

            fecha_legible = inspeccion_creada.fecha.strftime('%d/%m/%Y') if hasattr(inspeccion_creada.fecha, 'strftime') else inspeccion_creada.fecha
            conclusion_texto = inspeccion_creada.conclusion.strip() if inspeccion_creada.conclusion else 'Sin observaciones adicionales.'

            cuerpo_correo = "\n".join([
                "Cordial saludo,",
                "",
                f"Adjunto encontrará el informe de inspección técnica realizado el {fecha_legible} "
                f"para {cliente_obj.nombre}.",
                "",
                "Conclusión general del inspector:",
                conclusion_texto,
                "",
                "Quedamos atentos ante cualquier inquietud sobre el contenido de este informe.",
                "",
                "Atentamente,",
                "Roka Servicios Integrales",
            ])

            remitente = str(settings.DEFAULT_FROM_EMAIL)

            email = EmailMessage(
                subject=asunto,
                body=cuerpo_correo,
                from_email=remitente,
                to=lista_correos,
            )

            nombre_pdf = f"Inspeccion_{cliente_obj.nombre.replace(' ', '_')}_{inspeccion_creada.fecha}.pdf"
            email.attach(nombre_pdf, pdf_bytes, 'application/pdf')

            email.send(fail_silently=False)
            
            pdf_registro.enviado = True
            pdf_registro.save(update_fields=['enviado'])

            return JsonResponse({
                "status": "success",
                "message": f"Inspección guardada y enviada correctamente a: {', '.join(lista_correos)}"
            }, status=201)

        except Cliente.DoesNotExist:
            return JsonResponse({"status": "error", "message": "El cliente especificado no existe."}, status=404)
        except Exception as e:
            print(traceback.format_exc())
            return JsonResponse({"status": "error", "message": f"Error en el proceso: {str(e)}"}, status=500)

    return JsonResponse({"status": "error", "message": "Método no permitido."}, status=405)


tool = language_tool_python.LanguageTool('es')

@csrf_exempt
@login_required
@usuarios_en_grupos(['reportador_roka', 'admin_roka'])
def corregir_texto_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            texto_original = data.get('texto', '').strip()
            
            if not texto_original:
                return JsonResponse({'error': 'El texto está vacío'}, status=400)
            
            # 1. Le pasamos el texto a LanguageTool para que busque errores
            match_errors = tool.check(texto_original)
            
            # 2. Aplicamos todas las correcciones automáticas sugeridas
            texto_corregido = language_tool_python.utils.correct(texto_original, match_errors)
            
            # 3. Formateo extra: Asegurar que inicie con mayúscula si el corrector lo pasó por alto
            if texto_corregido:
                texto_corregido = texto_corregido[0].upper() + texto_corregido[1:]

            return JsonResponse({
                'textoCorregido': texto_corregido,
                'erroresEncontrados': len(match_errors) # Opcional, por si quieres saber cuántos corrigió
            })
            
        except Exception as e:
            print(f"Error en el corrector local: {str(e)}")
            return JsonResponse({'error': 'Error interno al procesar el texto'}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)