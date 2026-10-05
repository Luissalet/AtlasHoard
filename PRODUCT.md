# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Default pending the user's optional interface answer: local Python stdlib
HTTP server with static HTML/CSS/JavaScript, following Hoard Hub's lightweight
technology and shared theme. No build service, external font or CDN.

## Users

The owner of a Windows workstation and the local Hoard applications working
on that owner's projects. The owner also uses ordinary tools such as Paint
or GIMP on files in the shared folders.

## Product Purpose

Act as the common SSD of the Hoard ecosystem. Two applications must open the
same PNG at the same real filesystem path and observe native edits. Each
application can keep its native project format beside the shared assets.

## Operating Context

Local workstation. Hoard Hub discovers applications and authenticates calls;
Borges owns document indexing. Atlas owns shared project folders and metadata.
BookHoard and WatchHoard are independent and outside this scope.

## Capabilities and Constraints

- Ordinary filesystem directories, with stable paths and no mandatory copies.
- Explicit project membership and personal/work sphere; API permissions are
  cooperative and do not impose operating-system filesystem ACLs.
- Register saved files without rewriting them. Import an external file only
  on explicit request, without moving its source or replacing a destination.
- Reuse derived results only for matching source/output hashes and recipes.
- Never automatically migrate existing projects or scan unrelated user data.
- Default pending the optional organization answer: a folder per shared
  project, containing `shared/` and `hoards/<app>/` native project folders.
- Default storage location on this workstation: `D:\LocalAI\HoardStorage`;
  configurable on first launch, never silently changed for an existing store.

## Brand Commitments

Atlas's Hoard, consistent with the family's local application naming. Inherit
the Hoard theme and familiar file-management terminology. Spanish first.

## Evidence on Hand

No real user files have been moved. Automated examples and UI demonstration
projects are synthetic and must be identified as demonstration data.

## Product Principles

1. One shared live path for one working file.
2. Native tools and formats remain usable without Atlas.
3. Project membership and provenance accompany shared results.
4. File changes invalidate reuse rather than hiding stale work.
5. Local storage and explicit actions; no cloud dependency.
