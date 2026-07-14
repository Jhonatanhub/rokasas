from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q 
from reportador.models import Cliente
import traceback
from .models import Reunion
from django.contrib.auth.decorators import login_required
from django.db import transaction

class DashboardIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'reuniones/form.html'


def api_buscar_clientes(request):
    term = request.GET.get('q', '').strip()
    if term:
        resultado_clientes = Cliente.objects.filter(
            Q(nombre__icontains=term) | Q(nit__icontains=term)
        ).prefetch_related('correos_contacto')[:20]
    else:
        resultado_clientes = Cliente.objects.all().prefetch_related('correos_contacto')[:20]

    data = []
    for c in resultado_clientes:
        # Extraemos los correos asociados
        lista_correos = list(c.correos_contacto.values_list('correo', flat=True))
        
        data.append({
            'id': c.id,
            'nombre': c.nombre,
            'nit': c.nit,
            'administrador': getattr(c, 'administrador', '') or '',  
            'correos': lista_correos,
        })

    return JsonResponse(data, safe=False)


@login_required
def guardar_reunion(request):
    if request.method == "POST":
        try:
            # Envolver en transacción para asegurar la consistencia de los datos
            with transaction.atomic():
                cliente_id = request.POST.get('cliente_id')
                if not cliente_id:
                    return JsonResponse({"status": "error", "message": "No se seleccionó un cliente válido."}, status=400)
                
                # Validar la existencia del cliente
                cliente = Cliente.objects.get(id=cliente_id)
                
                # Extraer y limpiar los campos requeridos del POST
                fecha = request.POST.get('fecha')
                hora = request.POST.get('hora')
                notas = request.POST.get('notas')
                supervisor = request.POST.get('supervisor', 'Nicolas Gaviria Gonzalez')

                if not fecha or not hora or not notas:
                    return JsonResponse({"status": "error", "message": "Faltan campos obligatorios en el formulario."}, status=400)

                # Crear la instancia de la Reunión en la BD
                reunion = Reunion.objects.create(
                    cliente=cliente,
                    fecha=fecha,
                    hora=hora,
                    supervisor=supervisor,
                    notas=notas,
                    usuario=request.user  # Asignación correcta de la auditoría del usuario autenticado
                )

            return JsonResponse({
                "status": "success",
                "message": f"La reunión con {cliente.nombre} se guardó correctamente en el sistema."
            }, status=201)

        except Cliente.DoesNotExist:
            return JsonResponse({"status": "error", "message": "El cliente especificado no existe o fue eliminado."}, status=404)
        except Exception as e:
            print(traceback.format_exc())
            return JsonResponse({"status": "error", "message": f"Error interno en el servidor: {str(e)}"}, status=500)

    return JsonResponse({"status": "error", "message": "Método no permitido."}, status=405)