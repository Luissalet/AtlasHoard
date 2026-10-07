# External source references

Atlas can register an existing file outside a project as a live, read-only
input. The operator calls `atlas_file_link_source` with a project ID and an
absolute `source_path`; Atlas stores the resolved path, title, size and SHA-256
revision in the existing file registry. It does not copy, move or edit the
source. Sources inside the project should use `atlas_file_register` instead.

```json
{
  "name": "atlas_file_link_source",
  "arguments": {
    "project_id": "PROJECT_ID",
    "source_path": "D:/Research/reference.pdf",
    "app": "cicero",
    "title": "Reference PDF"
  }
}
```

The returned file has `external: true`, `input_readonly: true`, `source_path`,
`size`, and `revision`. A project member can pass its `file_id` to
`atlas_file_resolve` or `atlas_context`. Resolve refreshes the content hash and
size. Its response includes `changed`; a missing source is returned with
`state: "missing"` and `exists: false`. No project copy is created.

Atlas refuses a second link to the same source in a project, missing paths,
and paths already inside that project. A linked source cannot be registered as
a derived output. `atlas_file_import` remains available when a deliberate copy
into shared storage is wanted; ordinary `atlas_file_register` behavior is
unchanged.

`input_readonly` describes Atlas's file role and API behavior. It is not an OS
permission change: applications that can access the source path can still edit
it outside Atlas. Project membership controls Atlas API access, not filesystem
ACLs. Atlas does not watch sources continuously; resolve the file again after
external edits to refresh its revision.
