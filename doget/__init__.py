import json
import urllib.request
import urllib.error

DEFAULT_REGISTRY = "registry.ollama.ai"
BLOBS_PATTERN = "blobs"

def parse_model_name(model_name_input):
    tag = "latest"
    if ":" in model_name_input:
        base, tag = model_name_input.split(":", 1)
    else:
        base = model_name_input

    # Handle custom namespaces vs default 'library'
    if "/" in base:
        namespace, model = base.split("/", 1)
    else:
        namespace = "library"
        model = base
        
    return namespace, model, tag

def format_size(size_in_bytes):
    if not isinstance(size_in_bytes, (int, float)):
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            if unit == 'B':
                return f"{int(size_in_bytes)} {unit}"
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} PB"

def get_model_info(model_name_input):
    """
    Get both manifest and layer information for an Ollama model.
    
    Args:
        model_name_input: Model name in format '<model>:<tag>' or '<namespace>/<model>:<tag>'
    
    Returns:
        tuple: (manifest_dict, layers_list) where:
            - manifest_dict: The manifest JSON as a dictionary
            - layers_list: List of tuples [(layer_name, layer_url, layer_size), ...]
              where layer_name is the blob filename (e.g., 'sha256-xxxxx'),
              layer_url is the direct download URL, and layer_size is in bytes.
    
    Raises:
        ValueError: If model is not found on the registry
        RuntimeError: If there's a network or HTTP error
    """
    namespace, model, tag = parse_model_name(model_name_input)
    
    url = f"https://{DEFAULT_REGISTRY}/v2/{namespace}/{model}/manifests/{tag}"
    
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.docker.distribution.manifest.v2+json"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                raise RuntimeError(f"Registry returned status {response.status}")
            
            manifest = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Model '{model_name_input}' not found on the registry.")
        else:
            raise RuntimeError(f"HTTP Error fetching manifest: {e}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL Error fetching manifest: {e}")
    
    # Extract and process layers
    layers = manifest.get("layers", [])
    config = manifest.get("config")
    if config:
        layers.append(config)
    
    processed_layers = []
    for layer in layers:
        digest = layer.get("digest")
        size = layer.get("size")
        if digest:
            layer_url = f"https://{DEFAULT_REGISTRY}/v2/{namespace}/{model}/blobs/{digest}"
            layer_name = digest.replace(":", "-")  # sha256:xxxx -> sha256-xxxx
            processed_layers.append((layer_name, layer_url, size))
    
    return manifest, processed_layers