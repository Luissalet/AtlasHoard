# Referencias a fuentes externas

Atlas puede registrar un archivo existente fuera del proyecto como entrada
activa de solo lectura. El operador llama a `atlas_file_link_source` con el ID
del proyecto y una ruta absoluta `source_path`; Atlas guarda la ruta resuelta,
el título, el tamaño y la revisión SHA-256 en el registro de archivos actual.
No copia, mueve ni edita el original. Para archivos que ya están dentro del
proyecto se debe usar `atlas_file_register`.

```json
{
  "name": "atlas_file_link_source",
  "arguments": {
    "project_id": "ID_DEL_PROYECTO",
    "source_path": "D:/Research/reference.pdf",
    "app": "cicero",
    "title": "PDF de referencia"
  }
}
```

La respuesta incluye `external: true`, `input_readonly: true`, `source_path`,
`size` y `revision`. Un miembro puede pasar el `file_id` a
`atlas_file_resolve` o `atlas_context`. Resolve actualiza el hash y el tamaño;
su respuesta incluye `changed`. Si falta la fuente, devuelve `state: "missing"`
y `exists: false`. No se crea una copia en el proyecto.

Atlas rechaza una segunda referencia a la misma fuente en el mismo proyecto,
rutas inexistentes y rutas que ya están dentro del proyecto. Una fuente
enlazada no se puede registrar como resultado derivado. `atlas_file_import`
sigue disponible para crear una copia deliberada en la carpeta compartida; el
comportamiento normal de `atlas_file_register` no cambia.

`input_readonly` describe el papel del archivo y el comportamiento de la API de
Atlas. No cambia los permisos del sistema operativo: una aplicación que pueda
acceder a la ruta aún puede editarla fuera de Atlas. La pertenencia controla el
acceso a la API, no las ACL del sistema de archivos. Atlas no observa la fuente
continuamente; vuelve a resolverla después de una edición externa para
actualizar su revisión.
