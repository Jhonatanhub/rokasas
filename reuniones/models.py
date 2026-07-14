from django.conf import settings
from django.db import models

from reportador.models import Cliente


class Reunion(models.Model):
    # Información de la reunión
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="reuniones",
        verbose_name="Cliente"
    )

    fecha = models.DateField(
        verbose_name="Fecha de la reunión"
    )

    hora = models.TimeField(
        verbose_name="Hora de la reunión"
    )

    supervisor = models.CharField(
        max_length=150,
        verbose_name="Supervisor"
    )

    notas = models.TextField(
        verbose_name="Notas de la reunión"
    )

    # Auditoría
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reuniones",
        verbose_name="Creado por"
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación"
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Última actualización"
    )

    class Meta:
        verbose_name = "Reunión"
        verbose_name_plural = "Reuniones"
        ordering = ["-fecha", "-hora"]

    def __str__(self):
        return f"{self.cliente.nombre} - {self.fecha} {self.hora}"