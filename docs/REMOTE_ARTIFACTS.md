# Remote evidence recording transport

The GitHub connector rejects the largest (16 MB) recording as one blob. The remote repository therefore stores that recording in numbered binary parts with SHA-256 hashes. Run `python tools/restore_recording.py` to reconstruct the exact original; the source ZIP already contains the original recording. Other source files and evidence remain ordinary files. Failed smaller recordings are retained as historical evidence.

Reconstruction verifies every part and the complete recording before writing. This transport change does not change any browser assertion or its result.
