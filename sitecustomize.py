import os

_device = os.environ.get("OPENVINO_DEVICE")
if _device:
    try:
        import onnxruntime as _ort

        _OrigSession = _ort.InferenceSession

        class _OpenVINOSession(_OrigSession):
            def __init__(self, model, sess_options=None, providers=None,
                         provider_options=None, **kw):
                super().__init__(
                    model,
                    sess_options=sess_options,
                    providers=[
                        ("OpenVINOExecutionProvider", {"device_type": _device}),
                        "CPUExecutionProvider",
                    ],
                    provider_options=None,
                    **kw,
                )

        _ort.InferenceSession = _OpenVINOSession
    except Exception:
        pass
