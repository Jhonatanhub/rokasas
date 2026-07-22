from django.db import models
from django.conf import settings
from roka.storage_backends import (EvidenciasStorage, PDFInspeccionesStorage,)
import os
import uuid
from django.utils.text import slugify
from datetime import datetime, date


class Cliente(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Cliente")
    nit = models.CharField(max_length=20, unique=True, verbose_name="NIT")
    administrador = models.CharField(max_length=150, blank=True, null=True, verbose_name="Administrador")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class ClienteCorreo(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="correos_contacto")
    correo = models.EmailField(max_length=150, verbose_name="Correo Electrónico")
    
    class Meta:
        verbose_name = "Correo de Cliente"
        verbose_name_plural = "Correos de Clientes"
        unique_together = ('cliente', 'correo')

    def __str__(self):
        return f"{self.correo} ({self.cliente.nombre})"


# SECCIÓN CHANGER: Cabecera General del Informe
class Inspeccion(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="inspecciones", verbose_name="Cliente")
    fecha = models.DateField(verbose_name="Fecha")
    hora = models.TimeField(verbose_name="Hora")
    administrador = models.CharField(max_length=150, verbose_name="Administrador")
    supervisor = models.CharField(max_length=150, default="Nicolas Gaviria Gonzalez", verbose_name="Supervisor")
    correo = models.EmailField(verbose_name="Correo Electrónico")
    
    # Se pasa a la cabecera porque engloba a todo el reporte enviado
    conclusion = models.TextField(verbose_name="Conclusión General")
    
    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True
    )
    
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspecciones",
        verbose_name="Creado por"
    )
    

    class Meta:
        verbose_name = "Inspección"
        verbose_name_plural = "Inspecciones"
        ordering = ['-fecha', '-hora']

    def __str__(self):
        return f"{self.id} - {self.cliente.nombre}"


# NUEVO MODELO: Soporta los bloques dinámicos infinitos de tu JS
class InspeccionDetalle(models.Model):
    ENFOQUE_CHOICES = [
        ('Aseo y Limpieza', 'Aseo y Limpieza'),
        ('Seguridad y Salud en el Trabajo', 'Seguridad y Salud en el Trabajo'),
        ('Colaborador', 'Colaborador'),
        ('Otros', 'Otros'),
    ]

    CONCEPTO_CHOICES = [
        ('Zonas comunes', 'Zonas comunes'),
        ('Ascensores', 'Ascensores'),
        ('Paredes', 'Paredes'),
        ('Pasamanos', 'Pasamanos'),
        ('Escalas', 'Escalas'),
        ('Zonas verdes', 'Zonas verdes'),
        ('Otros', 'Otros'),
    ]

    CALIFICACION_CHOICES = [
        ('Excelente', 'Excelente'),
        ('Regular', 'Regular'),
        ('Mala', 'Mala'),
    ]

    inspeccion = models.ForeignKey(Inspeccion, on_delete=models.CASCADE, related_name="detalles")
    enfoque = models.CharField(max_length=100, choices=ENFOQUE_CHOICES, verbose_name="Enfoque de la inspección")
    concepto = models.CharField(max_length=100, choices=CONCEPTO_CHOICES, verbose_name="Concepto Técnico")
    calificacion = models.CharField(max_length=20, choices=CALIFICACION_CHOICES, verbose_name="Calificación")
    observacion = models.TextField(verbose_name="Observación")

    class Meta:
        verbose_name = "Detalle de Inspección"
        verbose_name_plural = "Detalles de Inspecciones"


# Ajustado para que las evidencias dependan del bloque específico (Detalle) y no de la cabecera general
def path_evidencias(instance, filename):
    """
    Estructura:
    evidencias/
        cliente_900123456/
            inspeccion_2026-07-17_125/
                zonas-comunes/
                    20260717_a8c4d19f2b.jpg
    """
    inspeccion = instance.detalle.inspeccion
    cliente = inspeccion.cliente

    extension = os.path.splitext(filename)[1].lower()

    # Normalizar la fecha por si viene en memoria como str o como date/datetime
    fecha_raw = inspeccion.fecha
    if isinstance(fecha_raw, (date, datetime)):
        fecha_obj = fecha_raw
    elif isinstance(fecha_raw, str) and fecha_raw.strip():
        try:
            fecha_obj = datetime.strptime(fecha_raw.strip(), "%Y-%m-%d").date()
        except ValueError:
            fecha_obj = date.today()
    else:
        fecha_obj = date.today()

    fecha_y2k = fecha_obj.strftime("%Y%m%d")
    fecha_iso = fecha_obj.strftime("%Y-%m-%d")

    nombre = (
        f"{fecha_y2k}_"
        f"{uuid.uuid4().hex[:10]}"
        f"{extension}"
    )

    carpeta_concepto = slugify(instance.detalle.concepto or 'general')
    carpeta_cliente = slugify(str(cliente.nit))

    return (
        f"cliente_{carpeta_cliente}/"
        f"inspeccion_{fecha_iso}_{inspeccion.id}/"
        f"{carpeta_concepto}/"
        f"{nombre}"
    )


class InspeccionEvidencia(models.Model):
    detalle = models.ForeignKey(
        InspeccionDetalle,
        on_delete=models.CASCADE,
        related_name="evidencias",
    )
    archivo = models.FileField(
        storage=EvidenciasStorage,
        upload_to=path_evidencias,
        max_length=255,
        verbose_name="Evidencia (Foto/Video)",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evidencia de Inspección"
        verbose_name_plural = "Evidencias de Inspecciones"

    def delete(self, *args, **kwargs):
        # Borra el blob en R2 al eliminar el registro; el modelo por sí solo
        # no elimina el archivo remoto, solo la fila en BD.
        self.archivo.delete(save=False)
        super().delete(*args, **kwargs)


def pdf_inspeccion_path(instance, filename):
    """
    Estructura:

    pdfs/
        inspecciones/
            cliente_900123456/
                2026/
                    2026-07-17_inspeccion_125.pdf
    """

    inspeccion = instance.inspeccion
    cliente = inspeccion.cliente
    carpeta_cliente = slugify(str(cliente.nit))

    return (
        f"cliente_{carpeta_cliente}/"
        f"{inspeccion.fecha.year}/"
        f"{inspeccion.fecha:%Y-%m-%d}_"
        f"inspeccion_{inspeccion.id}.pdf"
    )


class PDFInspeccion(models.Model):
    inspeccion = models.OneToOneField(
        Inspeccion,
        on_delete=models.CASCADE,
        related_name="pdf",
    )

    archivo = models.FileField(
        storage=PDFInspeccionesStorage,
        upload_to=pdf_inspeccion_path,
        max_length=255,
    )
    creado = models.DateTimeField(auto_now_add=True)
    enviado = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"PDF {self.inspeccion.id}"
    
