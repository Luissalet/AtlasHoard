# Anclas multimodales

Una ancla es un identificador estable de un lugar exacto dentro de una revisión
de un archivo registrado (interno o referencia externa de sólo lectura). Amplía
los archivos y revisiones que Atlas ya tiene; no hay un almacén aparte y Atlas
sigue sin modificar, copiar ni ejecutar nada. El ancla guarda una instantánea
pequeña de lo que había (cita con contexto, valores de celdas, hash del cuerpo de
un símbolo, textos del PDF con posición, huella de la malla) para poder volver a
encontrarlo sin conservar copias antiguas del archivo.

## Herramientas (HTTP `POST /api/agent/call` y MCP)

| Herramienta | Para qué |
| --- | --- |
| `atlas_anchor_create` | `file_id`, `kind`, `selector`, opcionales `label`, `comment`, `request_id`. Se crea sobre la revisión actual (se refresca antes). |
| `atlas_anchor_get` | Un ancla con su historia por revisión y sus comentarios. Sólo metadatos. |
| `atlas_anchor_list` | Por `file_id` o `project_id`; opcionales `revision` (número de secuencia o sha256, con `file_id`), `kind`, `status`, `limit`, `offset`. Devuelve resumen por estado y las revisiones vistas. |
| `atlas_anchor_resolve` | Refresca el archivo, vuelve a localizar el lugar y devuelve un bloque `open` para los clientes. |
| `atlas_anchor_comment` | Añade un comentario fijado a la revisión vigente en ese momento. |

`hoard://atlas/anchor/<id>` identifica un ancla y `hoard://atlas/file/<id>` el archivo.

## Selectores

| tipo | selector | archivos |
| --- | --- | --- |
| `text` | `{quote, prefix?, suffix?}`, `{start, end}` (desplazamientos de carácter) o `{line_start, line_end?, char_start?, char_end?}` (líneas desde 1) | cualquier texto UTF-8 (saltos de línea normalizados a `\n`) |
| `cell` | `{ref: "Hoja1!A1:B3"}` o `{sheet, range}` | `.csv`/`.tsv` (hoja `csv`), `.xlsx`/`.xlsm` |
| `pdf` | `{page, rect: [x0, y0, x1, y1]}` fracciones de página 0..1, origen arriba a la izquierda | `.pdf` (las posiciones del texto necesitan `pypdf`) |
| `image` | `{rect}` o `{x, y, w, h}` fracciones 0..1 | cualquier imagen (se leen tamaños PNG/JPEG/GIF/BMP) |
| `time` | `{start, end, duration?}` en segundos | audio/vídeo (se leen duraciones WAV y MP4/MOV/M4A) |
| `mesh` | `{node}` nombre o `{node_index}`, opcional `faces: [índices de triángulo]` | `.glb`, `.gltf`, `.obj` (`o`/`g`), `.stl` |
| `code` | `{symbol, line_start?}` (`Clase.método`) o `{line_start}` (Python) | Python con `ast`; otros lenguajes por heurística |

## Estado por revisión

Cuando se registra o refresca una revisión nueva del archivo, todas las anclas
anteriores se vuelven a resolver contra el contenido nuevo y el resultado se
guarda para esa revisión:

* `intact` (intacta): mismo lugar, mismo contenido.
* `moved` (movida): mismo contenido en otro sitio (cita y contexto, bloque de celdas, líneas del símbolo, texto del PDF desplazado o en otra página, índice de la pieza 3D).
* `changed` (cambiada): el lugar existe pero el contenido difiere (texto parecido por coincidencia aproximada, otros valores, otro cuerpo del símbolo, otra geometría, tamaño de imagen o duración distintos).
* `lost` (perdida): no se encuentra (cita desaparecida, hoja/símbolo/pieza ausente o renombrada, página inexistente, intervalo posterior al nuevo final).

Cada nueva resolución parte del selector original del ancla, de modo que un
archivo revertido vuelve a `intact`. La historia no se reescribe: el ancla conserva
su revisión de creación (`origin`), cada revisión observada tiene su propio estado
y un comentario hecho en la revisión 1 se queda en la revisión 1 y cuenta qué pasó
después (`comments[].status_at_revision`, `history`). Atlas sólo conoce las
revisiones que ha visto: cada vez que se registra, resuelve o usa un archivo en un contexto.

## Resultado de la resolución

`atlas_anchor_resolve` devuelve `status`, `detail`, `location`, `origin`, `history`,
`comments`, `file` y un objeto `open` con `path`, `file_uri`, `anchor_uri`,
`revision`, `revision_seq`, `current_revision_seq`, `viewable` y las claves propias
del tipo (`line_start`/`line_end`, `char_start`/`char_end`, `page`, `rect`,
`time_start`/`time_end`, `sheet`/`range`/`ref`, `symbol`, `node`/`faces`) más un
`fragment` (`page=3`, `t=2.5,4.0`, `L12-L14`, `Hoja1!A1:B3`). Con `revision`
devuelve el lugar en una revisión anterior ya observada; entonces `viewable` es
falso porque el archivo en disco ya no tiene ese contenido.

## Límites

* No se guarda el contenido de revisiones antiguas: las anclas se crean sobre la revisión actual y no existe estado de revisiones intermedias que Atlas no llegó a ver.
* Los archivos de más de 64 MiB no admiten anclas de texto, celdas, PDF, malla ni código; las de imagen y tiempo se aceptan sin comprobar tamaño ni duración.
* La coincidencia de texto en PDF necesita `pypdf`; sin él, el ancla de PDF sólo comprueba que la página existe. Un PDF escaneado no tiene texto que comparar.
* Las piezas 3D y los símbolos renombrados se consideran `lost`; no hay detección de renombrado. Los símbolos de código que no son Python y el final de cada bloque usan heurísticas.
* Se aplican las reglas de membresía de los archivos; es control de acceso de la API, no un sandbox del sistema operativo.
