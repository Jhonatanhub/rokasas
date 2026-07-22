from django.db import models
from django.conf import settings
from reportador.models import Cliente, Inspeccion  
from roka.storage_backends import PDFConsolidadosStorage
import os
import uuid
from django.utils.text import slugify
from datetime import datetime


class ConsolidadoCliente(models.Model):
    TIPO_CHOICES = [
        ("MENSUAL", "Mensual"),
        ("TRIMESTRAL", "Trimestral"),
        ("SEMESTRAL", "Semestral"),
        ("ANUAL", "Anual"),
        ("PERSONALIZADO", "Personalizado"),
    ]

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default="PERSONALIZADO"
    )
    
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
    
    
    
def pdf_consolidado_path(instance, filename):
    """
    Soporta fecha_inicio tanto si es tipo 'datetime.date' como si es 'str'.
    """
    consolidado = instance.consolidado
    cliente = consolidado.cliente
    carpeta_cliente = slugify(str(cliente.nit))

    fecha_ini = consolidado.fecha_inicio
    if isinstance(fecha_ini, str):
        fecha_ini = datetime.strptime(fecha_ini, '%Y-%m-%d').date()

    year = fecha_ini.year
    year_month = fecha_ini.strftime('%Y-%m')

    return (
        f"cliente_{carpeta_cliente}/"
        f"{year}/"
        f"consolidado_{consolidado.tipo.lower()}_"
        f"{year_month}_"
        f"{consolidado.id}.pdf"
    )


class PDFConsolidado(models.Model):
    consolidado = models.OneToOneField(
        ConsolidadoCliente,
        on_delete=models.CASCADE,
        related_name="pdf",
    )

    archivo = models.FileField(
        storage=PDFConsolidadosStorage,
        upload_to=pdf_consolidado_path,
        max_length=255,
    )

    creado = models.DateTimeField(auto_now_add=True)
    enviado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creado"]