from storages.backends.s3 import S3Storage


class EvidenciasStorage(S3Storage):
    """
    Almacenamiento para fotografías y videos de inspecciones.
    Público: se muestran directamente en galerías del frontend.
    Usa el dominio público de R2 (AWS_S3_CUSTOM_DOMAIN) definido en settings.
    """
    location = "evidencias"
    file_overwrite = False
    default_acl = None


class PDFInspeccionesStorage(S3Storage):
    """
    Almacenamiento para los PDF generados por el reportador.
    Privado: nunca se sirve por URL directa, solo se lee en backend
    para adjuntar al correo automático. No usa el dominio público.
    """
    location = "pdfs/inspecciones"
    file_overwrite = True
    default_acl = None
    custom_domain = False
    querystring_auth = False


class PDFConsolidadosStorage(S3Storage):
    """
    Almacenamiento para los PDF consolidados generados por el administrador.
    Privado: mismo criterio que PDFInspeccionesStorage.
    """
    location = "pdfs/consolidados"
    file_overwrite = True
    default_acl = None
    custom_domain = False
    querystring_auth = False