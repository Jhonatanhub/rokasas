from django.db import models
from django.conf import settings
from reportador.models import Cliente, Inspeccion  

class ConsolidadoCliente(models.Model):
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.CASCADE, 
        related_name="consolidados", 
        verbose_name="Cliente"
    )
    fecha_inicio = models.DateField(
        verbose_name="Fecha de Inicio"
    )
    fecha_fin = models.DateField(
        verbose_name="Fecha de Fin"
    )
    conclusion_general = models.TextField(
        blank=True, 
        verbose_name="Conclusión General"
    )
    administrador = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name="consolidados_generados",
        verbose_name="Generado por (Administrador)"
    )
    inspecciones = models.ManyToManyField(
        Inspeccion, 
        related_name="consolidados", 
        verbose_name="Inspecciones Incluidas"
    )
    
    # Auditoría automática estándar
    fecha_creacion = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Fecha de Generación"
    )

    class Meta:
        verbose_name = "Consolidado de Cliente"
        verbose_name_plural = "Consolidados de Clientes"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Consolidado {self.id} - {self.cliente.nombre} ({self.fecha_inicio} a {self.fecha_fin})"