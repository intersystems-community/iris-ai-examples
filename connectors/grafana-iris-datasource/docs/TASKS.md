# Phase A tasks (test first; each ends green)

- [x] T01 Capture real IRIS responses as fixtures; red test for the error object; fix `atelierStatus` (PA-01)
- [x] T02 Real-IRIS Go e2e (build tag `e2e`) + compose for an IRIS with a web server; run it (PA-02)
- [x] T03 Bump Go SDK to current; no `replace`; fix breakage (PA-03, PA-06)
- [x] T04 Pin `@grafana/*` to 11.x, `grafanaDependency >=11.1.0`; typecheck, build, jest (PA-03)
- [x] T05 Macros and variables in the backend, with unit tests; Table / Time series format (PA-04)
- [x] T06 Query editor: format selector, macro help; alerting flag; ErrorSource and limits (PA-05, PA-06)
- [ ] T07 Magefile, CI workflow, validator config; README/CHANGELOG/screenshots slots (PA-08)
- [ ] T08 Load into Grafana 11.1.0 and latest with real IRIS; screenshots (PA-07)
- [ ] T09 Run plugin-validator; fix Errors and Warnings (PA-09)
- [x] T06b Read-only by default: statement guard, "Allow data changes" setting, tests (PA-10)
- [ ] T10 Phase A report: what passes, what is left for Phase B
