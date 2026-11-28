# Python dependency vulnerability triage

Scan date: 2026-11-28. Tree: `main` @ `007ff9b` (re-run after BCM leftover removal).

This note triages known vulnerabilities in **Hermes Synapse Python dependencies**. It is an internal working document, not a product-security claim.

## Method

| Source | Result |
| --- | --- |
| `pip-audit` 2.10.1 on `uv export --frozen` of `backend/uv.lock` (PyPI advisory service) | **154** finding rows in **16** packages (matches the ~154 GitHub number) |
| Same scan, deduped by GHSA | **127** unique advisories |
| `osv-scanner` 2.7.1 on `backend/uv.lock` | 247 raw OSV records (PYSEC+GHSA aliases counted twice); used for CVSS. Lock has 139 packages (was 140 before `ta` was dropped). |
| GitHub Dependabot alerts | **Not accessible** — REST `403` "Dependabot alerts are disabled"; GraphQL `vulnerabilityAlerts.totalCount = 0` |
| `sandbox/requirements.txt` | Unpinned ranges; OSV transitive resolution aborted. Not in the 154. Compose image `pip install`s current PyPI at build. |
| npm (`frontend/` + `docs/`) | Out of scope here. `npm audit`: frontend 20 (8 high / 12 moderate); docs 7 (5 high / 2 moderate). |

`pip-audit` emits a row per PYSEC **and** GHSA for the same CVE, so 154 rows collapse to 127 unique GHSAs.

**What `007ff9b` changed vs `4432e7b`:** `ta` left `pyproject.toml`/`uv.lock`; compose `backend/Dockerfile` no longer pip-installs Twisted, simplefix, service_identity, pyOpenSSL, protobuf/grpcio-tools, scipy, mplfinance, plotly, or fredapi. Those Dockerfile extras were **never in `uv.lock`**, so they were not in the 154. A re-scan of the current lockfile is identical: same 16 packages, same 154 rows. `protobuf` remains only as a transitive of google-api / qdrant / onnxruntime / yfinance.

**Pilot configuration assumed throughout:** `docker compose up` (dashboard bound to `127.0.0.1:9119`, API only via nginx `/api`, FastAPI `auth_middleware` on `/api/*` except `/api/status`, OTP, `/api/plots/`). Backend is not published on the host network. Default LLM hosts (OpenRouter, Ollama) are ASCII.

**Lockfile vs compose:** CI/`uv sync` uses `backend/uv.lock`. The production `backend/Dockerfile` still installs floating `pkg>=...` ranges with pip (now aligned with pyproject plus `psycopg` and `psutil`), so a fresh compose build can already be *newer* than the lockfile (including, today, pypdf 7.x). The counts below are the lockfile GitHub sees.

## Summary counts

### pip-audit rows (154 — GitHub-comparable)

| Severity | Rows |
| --- | ---: |
| Critical | 9 |
| High | 91 |
| Medium | 47 |
| Low | 7 |
| **Total** | **154** |

### Unique GHSA (127)

| Severity | Unique advisories |
| --- | ---: |
| Critical | 8 |
| High | 73 |
| Medium | 41 |
| Low | 5 |
| **Total** | **127** |

### Packages with findings (`uv.lock`)

| Package | Locked | Unique advisories | Split |
| --- | --- | ---: | --- |
| `pillow` | 12.2.0 | 55 | 6 critical, 37 high, 12 medium |
| `pypdf` | 6.14.2 | 32 | 18 high, 13 medium, 1 low |
| `filelock` | 3.29.0 | 9 | 1 high, 6 medium, 2 low |
| `pyasn1` | 0.6.3 | 7 | 7 high |
| `soupsieve` | 2.8.4 | 6 | 2 high, 4 medium |
| `python-multipart` | 0.0.29 | 3 | 1 high, 2 low |
| `urllib3` | 2.7.0 | 3 | 2 high, 1 medium |
| `anyio` | 4.13.0 | 2 | 1 critical, 1 medium |
| `oauthlib` | 3.3.1 | 2 | 1 high, 1 medium |
| `starlette` | 1.1.0 | 2 | 1 high, 1 medium |
| `certifi` | 2026.6.17 | 1 | 1 critical |
| `cryptography` | 49.0.0 | 1 | 1 high |
| `fsspec` | 2026.4.0 | 1 | 1 high |
| `h2` | 4.3.0 | 1 | 1 medium |
| `hpack` | 4.1.0 | 1 | 1 medium |
| `httplib2` | 0.31.2 | 1 | 1 high |

## Critical and high findings

Reachability is for the **compose pilot** (localhost dashboard, authenticated FastAPI). "must-fix" means do it before a shared-host pilot; "can defer" means the path is not in our config or the fix is a major-version jump.

| Sev | Package | Current | CVE / GHSA | Fixed in | Reachable in our config? | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| critical | `anyio` | 4.13.0 | GHSA-82r6-8w77-94w6<br>CVE-2026-63374 | 4.14.2 | Partial — httpx/Starlette outbound TLS; IDNA spoof needs a non-ASCII LLM/API host (OpenRouter/Ollama are ASCII). | must-fix |
| critical | `certifi` | 2026.6.17 | GHSA-6q48-6c7w-9gw2 | 2026.10.18 | Partial — trust store used by httpx/requests; exploit needs the listed rogue CA to be used in a MITM. | must-fix |
| critical | `pillow` | 12.2.0 | GHSA-332p-7hrc-92wf | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| critical | `pillow` | 12.2.0 | GHSA-5x8w-8jj5-q52h<br>CVE-2026-112398 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| critical | `pillow` | 12.2.0 | GHSA-8g5g-8vmr-9782<br>CVE-2026-112403 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| critical | `pillow` | 12.2.0 | GHSA-v9pv-5gc8-w2m6<br>CVE-2026-96639 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| critical | `pillow` | 12.2.0 | GHSA-w889-685w-c8fh | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| critical | `pillow` | 12.2.0 | GHSA-xvh5-g6gv-559v<br>CVE-2026-112902 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `cryptography` | 49.0.0 | GHSA-g6cj-pr64-35w5<br>CVE-2026-69247 | 50.0.0 | No — PKCS7 decrypt APIs are unused; FastAPI/JWT path does not call them. | can defer |
| high | `filelock` | 3.29.0 | GHSA-v4x8-3wr5-3wq8 | 4.2.1 | No — HuggingFace cache locking only; SQLite ReadWriteLock is not on the request path. | can defer |
| high | `fsspec` | 2026.4.0 | GHSA-27vj-qcqg-25rc<br>CVE-2026-104851 | 2026.6.0 | No — ReferenceFileSystem is unused; fastembed/HF hub does not parse untrusted reference JSON. | can defer |
| high | `httplib2` | 0.31.2 | GHSA-j5g9-f88f-gfj3<br>CVE-2026-59939 | 0.32.0 | Partial — Google API client only; reachable if Google OAuth/API is configured and a malicious HTTP peer is contacted. | must-fix |
| high | `oauthlib` | 3.3.1 | GHSA-3jp2-3mrg-2vxc | 4.0.1 | Partial — Google OAuth token endpoint; not used in the default OTP-local pilot. | can defer |
| high | `pillow` | 12.2.0 | GHSA-22hg-r758-rrw9 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-27h8-gf7j-v5hc<br>CVE-2026-112392 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-3j72-p6qg-6xp7<br>CVE-2026-96642 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-4558-3h8r-v8xp<br>CVE-2026-112394 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-45hq-cxwh-f6vc<br>CVE-2026-55379 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-4rr5-89j8-mwwm<br>CVE-2026-112396 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-58r4-6rv3-gfh8<br>CVE-2026-112397 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-5x94-69rx-g8h2<br>CVE-2026-54060 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-5xm2-6676-qcp9 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-62p4-gmf7-7g93<br>CVE-2026-54058 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-65qm-jvmh-6pqg | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-6r8x-57c9-28j4<br>CVE-2026-59199 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-78g4-xqwv-q3g8 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-7mwm-ghpf-9vrm<br>CVE-2026-112402 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-8v84-f9pq-wr9x<br>CVE-2026-54059 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-9hw9-ch79-4vh6<br>CVE-2026-59205 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-9v9v-9qvf-h2hj<br>CVE-2026-96644 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-c6hw-5grf-ff96 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-cp9v-662q-vvx9<br>CVE-2026-112405 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-f2g6-542v-9j58 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-g4qv-2jxx-769h<br>CVE-2026-96643 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-g7cr-3p24-7wf7 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-g842-9rc4-69pw<br>CVE-2026-96637 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-gg2r-wvfm-q9rx | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-j4m9-6w36-pw47 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-jg86-v3jv-hrpm | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-jjj6-mw9f-p565<br>CVE-2026-59200 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-mrfp-p49p-3hf2 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-p4wg-p73j-c528 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-pchr-8j38-3x4p<br>CVE-2026-112896 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-pg7v-jwj7-p798<br>CVE-2026-59203 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-phj9-mv4w-65pm<br>CVE-2026-55380 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-q45j-58j2-45rg | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-vjc4-5qp5-m44j<br>CVE-2026-59204 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pillow` | 12.2.0 | GHSA-xcvg-w56q-r89m | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-xgh8-jp6q-p5x8<br>CVE-2026-112901 | 13.0.0 | No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. | can defer |
| high | `pillow` | 12.2.0 | GHSA-xj96-63gp-2gmr<br>CVE-2026-59197 | 12.3.0 | No decoder path on /api, but 12.3.0 is a patch; take it. Remaining issues need Pillow 13 (major) — defer those. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-2qm8-x737-gmw5 | 0.6.5 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-8ppf-4f7h-5ppj<br>CVE-2026-59885 | 0.6.4 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-9m75-vc3g-4x39 | 0.6.5 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-fm9c-5rcf-2q5p | 0.6.5 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-hm4w-wwcw-mr6r<br>CVE-2026-59886 | 0.6.4 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-m4p7-r5rc-7g4j<br>CVE-2026-59884 | 0.6.4 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pyasn1` | 0.6.3 | GHSA-mm57-4v3p-rchx | 0.6.5 | Partial — google-auth ASN.1/cert parsing; OTP pilot does not ingest untrusted BER. Safe patch still cheap. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-42gh-23hr-vphw | 6.21.3 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-4vqv-7265-gm2w | 6.21.3 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-5849-834g-hvw5 | 6.21.4 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-5jq2-8x83-x246<br>CVE-2026-102994 | 6.18.0 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-62m5-6wh8-28x7 | 6.21.3 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-6c7f-9265-g8fw | 6.21.2 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-cggf-277g-3q54 | 6.21.4 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-fp3h-c4fm-7vvf<br>CVE-2026-102995 | 6.18.1 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-g9cg-prrw-2r8q<br>CVE-2026-102996 | 6.18.1 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-gmh7-3g9r-mjh5 | 6.21.2 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-jr96-gvgh-j3r4 | 6.21.2 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-jw7q-gvrg-4vj3<br>CVE-2026-102997 | 6.18.1 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-mfr5-77xh-9j7h | 6.21.4 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-php9-fj8v-98fj<br>CVE-2026-102998 | 6.19.0 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-qv6h-rv94-w285<br>CVE-2026-102993 | 6.17.0 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-v247-6f48-mgcj<br>CVE-2026-102999 | 6.19.0 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-w23x-9jrw-r45c<br>CVE-2026-103000 | 6.19.0 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `pypdf` | 6.14.2 | GHSA-x3rh-gjgm-fmqc | 6.21.3 | Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. | must-fix |
| high | `python-multipart` | 0.0.29 | GHSA-5rvq-cxj2-64vf<br>CVE-2026-53539 | 0.0.30 | Yes — FastAPI File()/form parsing on /api/upload and /api/parse-pdf (auth required; dashboard is 127.0.0.1). | must-fix |
| high | `soupsieve` | 2.8.4 | GHSA-6655-6qjp-jx7x | 3.0.2 | No — BeautifulSoup is html.parser + get_text only; no CSS select() / soupsieve path. | can defer |
| high | `soupsieve` | 2.8.4 | GHSA-mmhr-3c5m-f64f | 4.0.0 | No — BeautifulSoup is html.parser + get_text only; no CSS select() / soupsieve path. | can defer |
| high | `starlette` | 1.1.0 | GHSA-82w8-qh3p-5jfq<br>CVE-2026-54283 | 1.3.1 | Yes — FastAPI request.form()/multipart for uploads; urlencoded DoS bypasses max_fields. | must-fix |
| high | `urllib3` | 2.7.0 | GHSA-8988-9cw3-xx77<br>CVE-2026-97687 | 2.8.0 | Partial — docker SDK, Qdrant, requests; TLS-proxy split only if an HTTPS proxy is configured. | must-fix |
| high | `urllib3` | 2.7.0 | GHSA-vxq7-64xx-v4gw<br>CVE-2026-97689 | 2.8.0 | Partial — docker SDK, Qdrant, requests; TLS-proxy split only if an HTTPS proxy is configured. | must-fix |

## Medium and low (grouped)

### Medium (41 unique)

- **anyio 4.13.0** — 1 unique advisory(ies); fixed in 4.14.2. Partial — httpx/Starlette outbound TLS; IDNA spoof needs a non-ASCII LLM/API host (OpenRouter/Ollama are ASCII). Priority: must-fix.
- **filelock 3.29.0** — 6 unique advisory(ies); fixed in 4.0.9, 4.2.1. No — HuggingFace cache locking only; SQLite ReadWriteLock is not on the request path. Priority: can defer.
- **h2 4.3.0** — 1 unique advisory(ies); fixed in 4.4.1. No — uvicorn serves HTTP/1.1 (h11) in compose; HTTP/2 h2 is not enabled. Priority: can defer.
- **hpack 4.1.0** — 1 unique advisory(ies); fixed in 4.2.0. No — HPACK is only used if HTTP/2 is enabled; it is not. Priority: can defer.
- **oauthlib 3.3.1** — 1 unique advisory(ies); fixed in 4.0.0. Partial — Google OAuth token endpoint; not used in the default OTP-local pilot. Priority: can defer.
- **pillow 12.2.0** — 12 unique advisory(ies); fixed in 12.3.0, 13.0.0. No — no first-party PIL import; matplotlib writes plots, it does not decode untrusted uploads on /api. Priority: can defer.
- **pypdf 6.14.2** — 13 unique advisory(ies); fixed in 6.15.0, 6.16.0, 6.16.1, 6.20.0, 6.20.1, 6.21.0. Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. Priority: must-fix.
- **soupsieve 2.8.4** — 4 unique advisory(ies); fixed in 2.10.0, 2.9.0, 3.0.2. No — BeautifulSoup is html.parser + get_text only; no CSS select() / soupsieve path. Priority: can defer.
- **starlette 1.1.0** — 1 unique advisory(ies); fixed in 1.3.0. Yes — FastAPI request.form()/multipart for uploads; urlencoded DoS bypasses max_fields. Priority: must-fix.
- **urllib3 2.7.0** — 1 unique advisory(ies); fixed in 2.8.0. Partial — docker SDK, Qdrant, requests; TLS-proxy split only if an HTTPS proxy is configured. Priority: must-fix.

### Low (5 unique)

- **filelock 3.29.0** — 2 unique advisory(ies); fixed in 4.2.1. No — HuggingFace cache locking only; SQLite ReadWriteLock is not on the request path. Priority: can defer.
- **pypdf 6.14.2** — 1 unique advisory(ies); fixed in 6.21.1. Yes — authenticated POST /api/parse-pdf and RAG PDF indexing call PdfReader on operator-supplied bytes. Priority: must-fix.
- **python-multipart 0.0.29** — 2 unique advisory(ies); fixed in 0.0.30, 0.0.31. Yes — FastAPI File()/form parsing on /api/upload and /api/parse-pdf (auth required; dashboard is 127.0.0.1). Priority: must-fix.

## Upgrade plan

Hours are engineering effort, not calendar time. Break-risk is for Hermes (FastAPI backend + compose pilot), not for the ecosystem in general.

| Group | What | Fixes (crit/high) | Hours | Break risk | Notes |
| --- | --- | --- | ---: | --- | --- |
| A. Safe lockfile patch/minor | `anyio 4.16.x`, `certifi 2026.11.x`, `python-multipart 0.0.34`, `urllib3 2.8.0`, `pyasn1 0.6.5`, `httplib2 0.32.1`, `pypdf 6.21.4` (not 7.x), `pillow 12.3.0` (not 13), `starlette 1.3.1` (not 1.10 / FastAPI 0.165), `fsspec 2026.6+` | All reachable crit/high with a patch/minor, plus some unreachable cheap ones | 4 | Low (starlette 1.1→1.3.1 is the only API-adjacent bump) | Must-fix before pilot. Keep pypdf <7 and pillow <13. |
| B. Pillow 13 | `pillow 13.0.0` | Remaining pillow critical/high decoder bugs | 6 | Medium — matplotlib/fastembed native wheels | **Defer:** no first-party `PIL` import; untrusted images are not decoded on `/api`. |
| C. Major transitives | `cryptography 50`, `filelock 4`, `oauthlib 4`, `soupsieve 3/4` | cryptography PKCS7; filelock RW-lock; oauthlib token grant; soupsieve ReDoS | 8 | Medium (OAuth + google-auth-oauthlib) | **Defer:** paths unused in OTP-local pilot. |
| D. FastAPI current | `fastapi 0.136 → 0.165` + `starlette 1.10` | Would pick up later Starlette fixes | 8 | High — 0.x FastAPI | Not required if A lands Starlette 1.3.1. |
| E. Pin Docker to the lockfile | Rewrite `backend/Dockerfile` `pip install pkg>=` to `uv sync --frozen` (or hashed requirements) | Stops compose from silently taking pypdf 7 / pillow 13 | 4 | Medium (first image that actually matches CI) | Recommended after A; not a vuln bump by itself. |
| F. Sandbox lock | Lock `sandbox/requirements.txt` (uv/pip-compile) and scan it | Unknown; sandbox is HITL-gated `execute_code` | 3 | Low–medium | Separate from the 154. |
| G. CI scan | Non-blocking `pip-audit` workflow on `uv.lock` | Detection, not fixes | 1 | None | Implement as `continue-on-error`. |
| H. npm (out of scope) | frontend 8 high + docs 5 high | N/A | 4 | Medium (Vite 8 / lock churn) | Not Python. |

### Total

| Scope | Hours |
| --- | ---: |
| Must-fix before pilot (Group A + G) | **5** |
| Remaining Python (B+C+D+E+F) | **29** |
| **All Python work in this note** | **34** |
| Optional npm (H) | +4 |

### Top must-fix items (pilot)

1. **python-multipart** `0.0.29 → 0.0.34` — urlencoded quadratic parse on FastAPI uploads (`GHSA-5rvq-cxj2-64vf`).
2. **starlette** `1.1.0 → 1.3.1` — `request.form()` ignores size limits on urlencoded bodies (`GHSA-82w8-qh3p-5jfq`).
3. **pypdf** `6.14.2 → 6.21.4` — crafted-PDF CPU/memory DoS on `/api/parse-pdf` (18 high GHSAs). Do **not** jump to 7.x in this pass.
4. **anyio** `4.13.0 → 4.16.x` — TLS IDNA cert spoof (`GHSA-82r6-8w77-94w6`, critical). Cheap; default hosts are ASCII.
5. **certifi** `2026.6.17 → 2026.11.x` — remove `emSign ECC Root CA - G3` (`GHSA-6q48-6c7w-9gw2`, critical). Cheap.
6. **urllib3** `2.7.0 → 2.8.0`, **pyasn1** `0.6.3 → 0.6.5`, **httplib2** `0.31.2 → 0.32.1` — patch/minor, low break risk.

Held back on purpose: Pillow 13, cryptography 50, filelock 4, oauthlib 4, soupsieve 3/4, FastAPI 0.165, pypdf 7.

## Held-back rationale (majors)

| Package | Jump | Why not for a "safe" pass |
| --- | --- | --- |
| pillow | 12.2 → 13.0 | Major; decoder CVEs need 13 but we never `Image.open` user bytes. 12.3.0 is the safe cap. |
| pypdf | 6.21 → 7.2 | Major. 6.21.4 covers the high/medium set above. |
| cryptography | 49 → 50 | Major. PKCS7 decrypt unused. |
| filelock | 3.29 → 4.x | Major. HuggingFace cache only. |
| oauthlib | 3.3 → 4.0 | Major. Google OAuth not in default OTP pilot. |
| soupsieve | 2.8 → 3/4 | Major for the two high ReDoS IDs; we never call `select()`. 2.10 is a minor for some mediums. |
| starlette/fastapi | 1.1 → 1.10 / 0.165 | FastAPI 0.x. 1.3.1 is the documented high-fix without taking 1.10. |

## Suggested CI (implemented on the upgrade branch only)

Non-blocking workflow: checkout, `astral-sh/setup-uv`, `uv export --frozen --no-hashes`, `pip-audit -r … --disable-pip --no-deps` with `continue-on-error: true` so it never gates merge. Do not add a blocking gate until the remaining majors are planned.
