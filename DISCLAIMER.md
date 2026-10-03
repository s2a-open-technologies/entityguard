# Disclaimer

**EntityGuard is not a certified medical device and not a certified data
protection tool.** It has not been cleared or approved by the FDA, does not
carry a CE mark under the EU Medical Device Regulation (MDR), and has not
undergone any equivalent regulatory review in any other jurisdiction.

EntityGuard is an open-source project (AGPL-3.0-or-later). Anyone may run,
modify, and deploy it. If you operate an instance of EntityGuard — for
yourself, your practice, your organization, or on behalf of others — **you
are solely responsible** for determining whether that use is lawful and for
ensuring compliance with all applicable medical device, data protection,
and healthcare regulations in your jurisdiction (e.g. MDR, HIPAA, GDPR)
before using it in any clinical, diagnostic, or patient-care context. The
original authors and contributors take no responsibility for how any
deployed instance is used.

**Automatic PII detection is inherently imperfect.** EntityGuard recognizes
entities via regex patterns and machine-learning models (spaCy, optional
transformer models). It can miss sensitive data (false negatives) and can
mask non-sensitive data (false positives). A missed entity means the
unmasked value reaches the downstream LLM. **Do not rely on EntityGuard as
the sole safeguard** for patient data. Operators must review the detection
configuration for their use case, keep models and patterns up to date, and
combine it with organizational and contractual measures (see
[`docs/data-mapping.md`](docs/data-mapping.md) and
[`SECURITY.md`](SECURITY.md)).

EntityGuard stores neither the analyzed text nor the placeholder mapping;
however, it is not a substitute for a legal review of your processing
activities or a data protection impact assessment (Art. 35 GDPR).

This software is provided "AS IS", without warranty of any kind, to the
maximum extent permitted by law — see [`LICENSE`](LICENSE)
(AGPL-3.0-or-later, §15–16) for the full warranty and liability disclaimer.
