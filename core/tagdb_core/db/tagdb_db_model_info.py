"""Model metadata extraction helpers for tagdb."""

import json
import logging

logger = logging.getLogger(__name__)


def extract_model_info(raw_meta_json: str | None, fmt: str) -> tuple[str | None, str | None]:
    """Extract model name and hash from metadata."""
    if not raw_meta_json:
        return (None, None)

    try:
        meta = json.loads(raw_meta_json)

        if fmt == 'nai' or 'model' in meta:
            model_name = meta.get('model')
            return (model_name, None)

        if 'Model' in meta:
            model_name = meta.get('Model')
            model_hash = meta.get('Model hash')
            return (model_name, model_hash)

        model_name = None

        if 'checkpoint' in meta:
            checkpoint = meta.get('checkpoint')
            if checkpoint and isinstance(checkpoint, str):
                checkpoint = checkpoint.replace('.safetensors', '').replace('.ckpt', '')
                model_name = checkpoint

        if not model_name and 'ckpt_name' in meta:
            ckpt_name = meta.get('ckpt_name')
            if ckpt_name and isinstance(ckpt_name, str):
                ckpt_name = ckpt_name.replace('.safetensors', '').replace('.ckpt', '')
                model_name = ckpt_name

        if not model_name and 'prompt' in meta:
            prompt_data = meta.get('prompt', {})
            if isinstance(prompt_data, dict):
                for node_data in prompt_data.values():
                    if isinstance(node_data, dict):
                        class_type = node_data.get('class_type', '')
                        inputs = node_data.get('inputs', {})

                        if 'CheckpointLoader' in class_type or 'Loader' in class_type:
                            if 'ckpt_name' in inputs:
                                ckpt = inputs.get('ckpt_name')
                                if ckpt and isinstance(ckpt, str):
                                    ckpt = ckpt.replace('.safetensors', '').replace('.ckpt', '')
                                    model_name = ckpt
                                    break
                            if 'checkpoint' in inputs:
                                ckpt = inputs.get('checkpoint')
                                if ckpt and isinstance(ckpt, str):
                                    ckpt = ckpt.replace('.safetensors', '').replace('.ckpt', '')
                                    model_name = ckpt
                                    break

                        if 'model' in inputs and isinstance(inputs.get('model'), str):
                            model_str = inputs['model']
                            if model_str.endswith(('.safetensors', '.ckpt')):
                                model_name = model_str.replace('.safetensors', '').replace('.ckpt', '')
                                break

                        if 'model_name' in inputs and isinstance(inputs.get('model_name'), str):
                            model_str = inputs['model_name']
                            if model_str.endswith(('.safetensors', '.ckpt')):
                                model_name = model_str.replace('.safetensors', '').replace('.ckpt', '')
                                break

        if not model_name and 'workflow' in meta:
            workflow_data = meta.get('workflow', {})
            if isinstance(workflow_data, dict) and 'model' in workflow_data:
                model_str = workflow_data.get('model')
                if isinstance(model_str, str):
                    model_name = model_str.replace('.safetensors', '').replace('.ckpt', '')

        if model_name:
            return (model_name, None)

        if not model_name and fmt == 'comfyui_flux':
            logger.debug(f"Could not extract model from ComfyUI metadata. Keys: {list(meta.keys())[:5]}")

    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"Error parsing metadata for model extraction: {e}")

    return (None, None)
