# Verification notes — v0.2 workflow

## Executed local checks

The release work used Windows/Python 3.12.3. The standard-library suite exercises original v0.1 controls plus direct cosine scores, subnormal normalization, early budget rejection, result requirements, comparable context, real subprocess redirection/broken pipes, report anchors/escaping and CI evidence generation. A separate optional environment used actual Faiss1.16.0, qdrant-client1.20.0 and NumPy2.5.5.

```sh
python -m unittest discover -s tests -v
python scripts/mutation_check.py
python -m unittest discover -s integrations -v
python scripts/ci_evidence.py --out ci-evidence
python -m examples.engine_capture --out engine-evidence
```

- The independent Fraction oracle enumerates optimal result sets rather than invoking production helpers to compute its expectation. It tests small integer L2/IP ranking and filtering, not all real-valued vectors.
- Named temporary-copy mutations remove or corrupt the relevant product behavior. The same named test first passes on clean code, then must produce an assertion failure on the mutant. Import/syntax/runtime crashes do not count as catching it. A real product ImportError negative control tests this distinction.
- The incompatible-context mutation initially triggered both assertion failures and a KeyError in a broad test. The harness correctly refused to count that mixed result; a focused corpus-change test now isolates its intended assertion. The broad context test remains. The rejection predicate was not loosened.
- The owner found and reproduced two further issues during integration: all-eligible context fingerprint construction expanded IDs once per query, and an error could append through stderr when both streams aliased an input. Both received red-first regression tests and corresponding focused corrections.
- Real engine tests cover L2/IP/cosine, actual Qdrant local payload filtering, actual Faiss padding, wrong score encoding, and reversed exports. The optional suite fails when its dependencies are missing; it does not silently skip.
- `ci_evidence.py` retains separately observed exit0/PASS, exit1/FAIL and exit2/ERROR. Negative examples are deliberate defects, not upstream engine bug discoveries.

## Review provenance

Two independent pre-implementation read-only audits provided reproducible findings. The owner implemented fixes and additional workflows. Two independent post-implementation review attempts were blocked before execution by service limits; **no post-change independent approval is claimed for v0.2**. Final review and reproducible verification are owner-run. This limitation is distinct from the earlier v0.1 review and is not concealed by a passing test count.

## Reproduce package acceptance

```sh
python -m pip install build
python -m build
python scripts/smoke_wheel.py dist/vector_result_audit-0.2.2-py3-none-any.whl
```

The smoke script creates a fresh venv outside the repository, removes PYTHONPATH/PYTHONHOME, installs only the selected wheel with `--no-index --no-deps`, runs its console/module commands and checks an actual -0.5 comparison delta and generated HTML. It does not install the optional engines or test against an editable checkout. A bad wheel or wrong exit status fails the verifier. As a negative control, running the new verifier on the preserved v0.1.0 wheel failed at the real missing `compare` command (expected exit1, observed exit2); the v0.2 wheel completed the same workflow. The publicly generated example has a byte-for-byte `--check` mode to reject a stale preview:

```sh
python -m scripts.build_demo --out docs/index.html --check
```

## CI evidence, not badges as proof

The checked-in workflow runs the zero-dependency suite and wheel smoke on Ubuntu/Windows with Python3.10/3.12, plus separate pinned real-engine jobs on Python3.12. Official actions are pinned to inspected commit IDs. JSON/HTML control artifacts are uploaded even if a previous test failed; failed gate exit codes are not swallowed. Remote completion is only established by the actual [Actions run](https://github.com/gedouluhui/vector-result-audit/actions) for the published commit, not by this document or workflow syntax.

## What these checks do not establish

No real customer export, Qdrant server cluster, approximate-index workload, production ACL, stale-snapshot recovery, embedding relevance, throughput superiority, external adoption or star growth was measured. Near-tie floating-point behavior still depends on the explicit reference policy. An identical context fingerprint proves equality of declared normalized context, not authenticity of the underlying data. Browser checks do not substitute for assistive-technology/user studies or every browser engine.
