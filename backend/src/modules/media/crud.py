from fastcrud import FastCRUD

from .models import Media, Mediable

crud_media: FastCRUD = FastCRUD(Media)
crud_mediables: FastCRUD = FastCRUD(Mediable)
