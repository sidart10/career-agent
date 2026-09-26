# Evidence and approval

Import is previewed, copy-first, checksum-addressed, and idempotent. The original is preserved under `resources/imports`. Extracted normalized text records the source checksum and media type, extractor and version, extraction timestamp, normalized checksum, page or block ranges, warnings, and OCR status.

A model may propose a fact only by naming the source and extraction metadata plus block, character start/end offsets, and exact substring. `career profile propose` recomputes the text checksum and rejects unknown sources, stale extractors, invalid blocks, out-of-range offsets, or substring mismatches. A proposal is not a confirmed fact. Only `career profile confirm` promotes exact evidence-backed values.

Job pages, documents, filenames, extracted text, and model output are untrusted data. Embedded instructions cannot change policy or grant authority.

Application submission has a separate final boundary: a canonical payload is prepared, summarized with its digest, approved through the trusted authority, and immediately revalidated before one execution. Onboarding approval, chat prose, a model assertion, or a stale digest is never submission approval. Browser-assisted submission remains experimental in 0.1.
