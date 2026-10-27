# Third-party software and data

Original Stage 0/1 sources and history are retained from the user's WorkBuddy project. MIT applies to project-owned source; it does not relicense dependencies or third-party data.

Runtime dependencies: Shapely (BSD), pyproj (MIT), PyYAML (MIT), Pydantic (MIT), jsonschema (MIT), GeoPandas (BSD), pandas (BSD), NumPy (BSD). Consult each installed distribution's license for the exact version and transitive dependency notices, including GEOS/PROJ/GDAL dependencies. Dependencies are installed rather than vendored in the source ZIP.

DOM test dependency: linkedom (ISC), installed separately via npm. No external map tiles/fonts/CDN assets are needed by the UI.

Synthetic examples and generated benchmark data are project-authored. Generator labels are developer-visible, not an independent blind benchmark.

Public point example: US Geological Survey earthquake feed. Source URL, retrieval timestamp, SHA-256, feature count and transformation disclosure are in data/public/SOURCE.json. USGS-authored data are generally public domain; source-specific third-party credits remain applicable. This is an IO/quality demonstration, not a known-defect benchmark and not customer facility data.

Upstream website: https://earthquake.usgs.gov/earthquakes/feed/v1.0/
Rights: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits

Local runtime option: Ollama v0.40.11 (official GitHub portable release, MIT) and Qwen3 4B Q4_K_M (model metadata reports Apache License 2.0). Binaries/weights are downloaded into excluded work storage and are not redistributed in the source ZIP. Installation provenance and model digest are recorded in acceptance/stage-4/local-model/installation.json.
