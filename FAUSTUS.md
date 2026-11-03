# Atlas's Hoard para Faustus

Disco compartido local de la familia Hoard: proyectos con archivos compartidos
vivos y carpetas nativas por Hoard, revisiones por hash, referencias externas de
sólo lectura y resultados derivados reutilizables. Atlas no ejecuta
transformaciones y no modifica los originales.

## Anclas multimodales (propuesta de investigación 22)

Un ancla es un identificador estable que apunta a un lugar exacto de una revisión
de un archivo registrado, para que Faustus u otro Hoard pueda saltar allí.

* Herramientas MCP/REST: `atlas_anchor_create`, `atlas_anchor_get`, `atlas_anchor_list`, `atlas_anchor_resolve`, `atlas_anchor_comment`.
* Tipos: `text`, `cell` (csv/xlsx), `pdf` (página + rectángulo normalizado), `image`, `time`, `mesh` (GLB/OBJ/STL) y `code` (Python por `ast`, otros por heurística).
* Cada ancla guarda el hash y el número de la revisión en que se creó, una etiqueta, un comentario opcional y una instantánea del contenido.
* Al registrarse o refrescarse una revisión nueva, cada ancla se vuelve a resolver y queda `intact`, `moved`, `changed` o `lost` para esa revisión. La historia nunca se reescribe: un comentario hecho en la revisión 1 sigue en la revisión 1 e indica qué pasó en la 2.
* `atlas_anchor_resolve` devuelve el bloque `open` (ruta, URI, revisión, página/rectángulo, tiempo, celda, líneas del símbolo, nodo de malla, `viewable`, `fragment`).
* Para saltar a un lugar: llama a `atlas_anchor_resolve` y abre `open.path` en el lugar indicado; si `open.viewable` es falso, esa revisión ya no es el archivo en disco.
* Interfaz: pestaña **Anclas / Anchors** del proyecto (español de España e inglés según el navegador).
* Límites: no se guardan copias de revisiones antiguas; archivos de más de 64 MiB sin anclas de texto/celdas/PDF/malla/código; PDF con texto requiere `pypdf`; no se detectan renombrados de nodos ni símbolos (se informan como `lost`).
* El allowlist de herramientas del Hub (`family-services.json` de HoardLink) debe ampliarse en el repositorio de HoardLink para que otros Hoards llamen a las herramientas de anclas a través del Hub; la copia vendida no se edita aquí.

Documentación: `docs/ANCHORS.es.md` y `docs/ANCHORS.md`.
