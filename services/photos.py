"""Validated photographs stored inside the backed-up database."""
import io
import warnings
import uuid
from PIL import Image, ImageOps, ImageDraw, UnidentifiedImageError
from db import connect
from utils.dates import timestamp

OWNERS={'sku':'inventory_skus','product':'catalog_products','component':'catalog_components'}
MAX_BYTES=10*1024*1024

def thumbnail(content=None):
    """Display-only letterbox; retain the original normalized photo in storage."""
    canvas=Image.new('RGBA',(600,400),(0,0,0,0))
    if content:
        with Image.open(io.BytesIO(content)) as original:
            fitted=ImageOps.contain(original.convert('RGBA'),canvas.size,Image.Resampling.LANCZOS)
            canvas.alpha_composite(fitted,((canvas.width-fitted.width)//2,(canvas.height-fitted.height)//2))
    else:
        draw=ImageDraw.Draw(canvas)
        color='#8C9DA6'
        draw.rounded_rectangle((250,175,350,239),radius=9,outline=color,width=3)
        draw.line((272,175,280,162,321,162,329,175),fill=color,width=3)
        draw.ellipse((281,188,319,226),outline=color,width=3)
    output=io.BytesIO();canvas.save(output,'PNG');return output.getvalue()

def normalize(content):
    if not isinstance(content,bytes) or not content or len(content)>MAX_BYTES:
        raise ValueError('Selecciona una foto de hasta 10 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as original:
                if original.format not in ('JPEG','PNG','WEBP') or original.width*original.height>24_000_000:
                    raise ValueError('Usa JPG, PNG o WebP de hasta 24 megapíxeles.')
                original.load()
                image=ImageOps.exif_transpose(original)
                image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
                transparent='A' in image.getbands() or 'transparency' in image.info
                image=image.convert('RGBA' if transparent else 'RGB')
                output=io.BytesIO()
                image.save(output,format='PNG' if transparent else 'JPEG',**({} if transparent else {'quality':88}))
                return output.getvalue(),'image/png' if transparent else 'image/jpeg',image.width,image.height
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError('No se pudo leer la foto. Selecciona un archivo JPG, PNG o WebP válido.') from exc

def _owner(kind,identity):
    if kind not in OWNERS or isinstance(identity,bool) or not isinstance(identity,int) or identity<=0:
        raise ValueError('Referencia de foto no válida.')
    return kind+'_id'

def get(kind,identity):
    field=_owner(kind,identity)
    with connect() as conn:
        row=conn.execute(f'SELECT * FROM product_photos WHERE {field}=?',(identity,)).fetchone()
        return dict(row) if row else None

def for_sku(row):
    return get('sku',row['id']) or (get('component',row['component_id']) if row.get('component_id') else None)

def save(kind,identity,content,*,expected_revision=None):
    field=_owner(kind,identity)
    normalized,mime,width,height=normalize(content)
    with connect(write=True) as conn:
        if not conn.execute(f'SELECT 1 FROM {OWNERS[kind]} WHERE id=?',(identity,)).fetchone():
            raise ValueError('La referencia ya no existe. Actualiza la vista.')
        old=conn.execute(f'SELECT revision FROM product_photos WHERE {field}=?',(identity,)).fetchone()
        if (old[0] if old else None)!=expected_revision:
            raise ValueError('La foto cambió en otra ventana. Vuelve a abrir su edición.')
        conn.execute(f'''INSERT INTO product_photos({field},content,mime,width,height,revision,updated_at)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT({field}) DO UPDATE SET content=excluded.content,
          mime=excluded.mime,width=excluded.width,height=excluded.height,revision=excluded.revision,updated_at=excluded.updated_at''',
          (identity,normalized,mime,width,height,uuid.uuid4().hex,timestamp()))

def remove(kind,identity,*,expected_revision):
    field=_owner(kind,identity)
    with connect(write=True) as conn:
        row=conn.execute(f'SELECT revision FROM product_photos WHERE {field}=?',(identity,)).fetchone()
        if not row or row[0]!=expected_revision: raise ValueError('La foto cambió. Vuelve a abrir su edición.')
        conn.execute(f'DELETE FROM product_photos WHERE {field}=?',(identity,))
