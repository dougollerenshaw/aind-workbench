import argparse
import json
import traceback
from flask import Flask, render_template_string, request, jsonify
from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AIND Metadata Upgrader Tool</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
        }
        .input-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #555;
        }
        input[type="text"] {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
            box-sizing: border-box;
        }
        button {
            background-color: #007bff;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #0056b3;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        #results {
            margin-top: 30px;
        }
        .success {
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .error {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .info {
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            color: #0c5460;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .upgrade-details {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            font-family: monospace;
            margin-top: 10px;
        }
        .upgrade-item {
            padding: 5px 0;
            border-bottom: 1px solid #dee2e6;
        }
        .upgrade-item:last-child {
            border-bottom: none;
        }
        pre {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .loading {
            color: #666;
            font-style: italic;
        }
        .asset-info {
            background-color: #e7f3ff;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .asset-info h3 {
            margin-top: 0;
            color: #004085;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AIND Metadata Upgrader Tool</h1>
        <p class="subtitle">Test if an asset can upgrade from schema v1 to v2</p>
        
        <div class="input-group">
            <label for="assetId">Asset ID or Name:</label>
            <input type="text" id="assetId" placeholder="e.g., 733a1052-683c-46d2-96ca-8f89bd270192 or behavior_689727_2024-02-07_15-01-36">
        </div>
        
        <button onclick="checkUpgrade()">Check Upgrade</button>
        
        <div id="results"></div>
    </div>

    <script>
        function checkUpgrade() {
            const assetId = document.getElementById('assetId').value.trim();
            const resultsDiv = document.getElementById('results');
            
            if (!assetId) {
                resultsDiv.innerHTML = '<div class="error">Please enter an asset ID or name</div>';
                return;
            }
            
            resultsDiv.innerHTML = '<div class="loading">Checking upgrade...</div>';
            
            fetch('/check_upgrade', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ asset_id: assetId })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    resultsDiv.innerHTML = `<div class="error"><strong>Error:</strong> ${data.error}</div>`;
                } else {
                    displayResults(data);
                }
            })
            .catch(error => {
                resultsDiv.innerHTML = `<div class="error"><strong>Error:</strong> ${error.message}</div>`;
            });
        }
        
        function displayResults(data) {
            const resultsDiv = document.getElementById('results');
            let html = '';
            
            // Asset info
            html += '<div class="asset-info">';
            html += '<h3>Asset Information</h3>';
            html += `<div><strong>ID:</strong> ${data.asset_id}</div>`;
            html += `<div><strong>Name:</strong> ${data.asset_name}</div>`;
            html += `<div><strong>Created:</strong> ${data.created}</div>`;
            html += '</div>';
            
            // Upgrade result
            if (data.success) {
                html += '<div class="success">';
                html += '<h3>✓ Upgrade Successful!</h3>';
                html += '<p>This asset can be upgraded to schema v2.</p>';
                html += '</div>';
                
                // Show what was upgraded
                if (data.upgraded_files && data.upgraded_files.length > 0) {
                    html += '<div class="upgrade-details">';
                    html += '<h4>Upgraded Files:</h4>';
                    data.upgraded_files.forEach(file => {
                        html += `<div class="upgrade-item">${file}</div>`;
                    });
                    html += '</div>';
                }
            } else {
                html += '<div class="error">';
                html += '<h3>✗ Upgrade Failed</h3>';
                html += `<p><strong>Error:</strong> ${data.error_message}</p>`;
                html += '</div>';
                
                // Show which file failed
                if (data.failed_file) {
                    html += '<div class="info">';
                    html += `<strong>Failed during:</strong> ${data.failed_file} upgrade`;
                    html += '</div>';
                }
                
                // Show full traceback
                if (data.traceback) {
                    html += '<details><summary style="cursor: pointer; font-weight: bold;">Show Full Error Details</summary>';
                    html += `<pre>${data.traceback}</pre>`;
                    html += '</details>';
                }
            }
            
            resultsDiv.innerHTML = html;
        }
        
        // Allow Enter key to trigger check
        document.getElementById('assetId').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                checkUpgrade();
            }
        });
    </script>
</body>
</html>
"""


def get_mongodb_client():
    """Create a MongoDB client for production v1 database"""
    return MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets"
    )


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/check_upgrade', methods=['POST'])
def check_upgrade():
    try:
        data = request.json
        asset_identifier = data.get('asset_id', '').strip()
        
        if not asset_identifier:
            return jsonify({'error': 'Asset ID or name is required'}), 400
        
        # Connect to database
        client = get_mongodb_client()
        
        # Try to find asset by ID or name
        if len(asset_identifier) == 36 and '-' in asset_identifier:
            # Looks like a UUID
            query = {"_id": asset_identifier}
        else:
            # Assume it's a name
            query = {"name": asset_identifier}
        
        records = client.retrieve_docdb_records(filter_query=query, limit=1)
        
        if not records:
            return jsonify({'error': f'Asset not found: {asset_identifier}'}), 404
        
        asset_data = records[0]
        asset_id = asset_data.get('_id', 'Unknown')
        asset_name = asset_data.get('name', 'Unknown')
        created = asset_data.get('created', 'Unknown')
        
        # Try to upgrade
        try:
            upgrader = Upgrade(asset_data)
            upgraded_data = upgrader.upgrade()
            
            # Find what was upgraded
            upgraded_files = []
            for key in upgraded_data.keys():
                if key in asset_data and upgraded_data[key] != asset_data[key]:
                    upgraded_files.append(key)
                elif key not in asset_data:
                    upgraded_files.append(f"{key} (new)")
            
            return jsonify({
                'success': True,
                'asset_id': asset_id,
                'asset_name': asset_name,
                'created': created,
                'upgraded_files': upgraded_files
            })
            
        except Exception as e:
            # Parse the error to find which file failed
            error_str = str(e)
            tb = traceback.format_exc()
            
            # Try to extract which file was being upgraded
            failed_file = None
            if 'Upgrading' in tb:
                lines = tb.split('\n')
                for line in lines:
                    if 'Upgrading' in line:
                        failed_file = line.strip()
                        break
            
            return jsonify({
                'success': False,
                'asset_id': asset_id,
                'asset_name': asset_name,
                'created': created,
                'error_message': error_str,
                'failed_file': failed_file,
                'traceback': tb
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AIND Metadata Upgrader Tool')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host address to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5001,
                        help='Port to bind to (default: 5001)')
    
    args = parser.parse_args()
    
    print(f"Starting AIND Metadata Upgrader Tool on {args.host}:{args.port}")
    print(f"Access at: http://localhost:{args.port}")
    
    app.run(host=args.host, port=args.port, debug=True)
