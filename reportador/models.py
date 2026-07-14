from django.db import models
from django.conf import settings


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
    return f"inspecciones/{instance.detalle.inspeccion.id}/evidencias/{filename}"

class InspeccionEvidencia(models.Model):
    detalle = models.ForeignKey(InspeccionDetalle, on_delete=models.CASCADE, related_name="evidencias", null=True, blank=True)
    archivo = models.FileField(upload_to=path_evidencias, verbose_name="Evidencia (Foto/Video)")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = "Evidencia de Inspección"
        verbose_name_plural = "Evidencias de Inspecciones"