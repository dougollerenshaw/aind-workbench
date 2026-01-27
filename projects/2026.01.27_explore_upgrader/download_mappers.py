"""Download the mapper files from GitHub"""

import requests

files_to_fetch = [
    {
        "url": "https://raw.githubusercontent.com/AllenNeuralDynamics/aind-metadata-mapper/dev/src/aind_metadata_mapper/fip/session.py",
        "output": "old_mapper_session.py"
    },
    {
        "url": "https://raw.githubusercontent.com/AllenNeuralDynamics/aind-metadata-mapper/release-v1.0.0/src/aind_metadata_mapper/fip/mapper.py",
        "output": "new_mapper.py"
    }
]

for file_info in files_to_fetch:
    print(f"Fetching {file_info['url']}...")
    response = requests.get(file_info["url"])
    if response.status_code == 200:
        with open(file_info["output"], "w") as f:
            f.write(response.text)
        print(f"  Saved to {file_info['output']}")
    else:
        print(f"  Failed: {response.status_code}")
