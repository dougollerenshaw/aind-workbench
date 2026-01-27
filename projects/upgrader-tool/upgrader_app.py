import argparse
from flask import Flask, render_template_string, request, jsonify
from upgrade import upgrade_asset

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
            
            // Use relative path so it works regardless of mount point
            fetch('check_upgrade', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ asset_id: assetId })
            })
            .then(response => {
                // Check if response is JSON
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return response.json();
                } else {
                    // Not JSON, probably an HTML error page
                    return response.text().then(text => {
                        throw new Error(`Server returned non-JSON response (status ${response.status}). Check terminal for errors.`);
                    });
                }
            })
            .then(data => {
                if (data.error) {
                    let errorHtml = `<div class="error"><strong>Error:</strong> ${data.error}`;
                    if (data.traceback) {
                        errorHtml += '<details><summary style="cursor: pointer; margin-top: 10px; font-weight: bold;">Show Full Traceback</summary>';
                        errorHtml += `<pre>${data.traceback}</pre>`;
                        errorHtml += '</details>';
                    }
                    errorHtml += '</div>';
                    resultsDiv.innerHTML = errorHtml;
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
                html += '<h3>All Files Upgraded Successfully!</h3>';
                html += '<p>This asset can be fully upgraded to schema v2.</p>';
                html += '</div>';
                
                // Show what was upgraded
                if (data.upgraded_files && data.upgraded_files.length > 0) {
                    html += '<div class="upgrade-details">';
                    html += '<h4>Files That Changed:</h4>';
                    html += '<ul>';
                    data.upgraded_files.forEach(file => {
                        html += `<li>${file}</li>`;
                    });
                    html += '</ul>';
                    html += '</div>';
                }
                
                // Show unchanged files
                if (data.unchanged_files && data.unchanged_files.length > 0) {
                    html += '<div class="info">';
                    html += '<h4>Files Already Up-to-Date:</h4>';
                    html += '<ul>';
                    data.unchanged_files.forEach(file => {
                        html += `<li>${file}</li>`;
                    });
                    html += '</ul>';
                    html += '</div>';
                }
            } else {
                // Partial or complete failure
                if (data.partial_success) {
                    html += '<div class="error">';
                    html += '<h3>Partial Upgrade Failure</h3>';
                    html += '<p>Some files can be upgraded, but others have errors.</p>';
                    html += '</div>';
                } else {
                    html += '<div class="error">';
                    html += '<h3>Upgrade Failed</h3>';
                    html += '<p>Unable to upgrade this asset to schema v2.</p>';
                    html += '</div>';
                }
                
                // Show successful upgrades if any
                if (data.upgraded_files && data.upgraded_files.length > 0) {
                    html += '<div class="success">';
                    html += '<h4>Successfully Upgraded:</h4>';
                    html += '<ul>';
                    data.upgraded_files.forEach(file => {
                        html += `<li>${file}</li>`;
                    });
                    html += '</ul>';
                    html += '</div>';
                }
                
                // Show unchanged files if any
                if (data.unchanged_files && data.unchanged_files.length > 0) {
                    html += '<div class="info">';
                    html += '<h4>Already Up-to-Date:</h4>';
                    html += '<ul>';
                    data.unchanged_files.forEach(file => {
                        html += `<li>${file}</li>`;
                    });
                    html += '</ul>';
                    html += '</div>';
                }
                
                // Show all errors
                if (data.errors && data.errors.length > 0) {
                    html += '<div class="error">';
                    html += '<h4>Failed Files:</h4>';
                    data.errors.forEach(err => {
                        html += '<div style="margin-bottom: 20px; border-left: 3px solid #dc3545; padding-left: 10px;">';
                        html += `<h5 style="margin: 5px 0;">${err.file}</h5>`;
                        html += `<p style="margin: 5px 0;"><strong>Error:</strong> ${err.error}</p>`;
                        html += '<details style="margin-top: 10px;"><summary style="cursor: pointer; font-weight: bold;">Show Full Traceback</summary>';
                        html += `<pre style="font-size: 12px; overflow-x: auto;">${err.traceback}</pre>`;
                        html += '</details>';
                        html += '</div>';
                    });
                    html += '</div>';
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


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/check_upgrade', methods=['POST'])
def check_upgrade():
    """Check if an asset can be upgraded"""
    data = request.json
    asset_identifier = data.get('asset_id', '').strip()
    
    if not asset_identifier:
        return jsonify({'error': 'Asset ID or name is required'}), 400
    
    print(f"\n{'='*60}")
    print(f"Checking upgrade for: {asset_identifier}")
    print(f"{'='*60}")
    
    # Call the standalone upgrade function
    result = upgrade_asset(asset_identifier)
    
    if 'error' in result and 'traceback' not in result:
        # Asset not found error
        return jsonify(result), 404
    
    if result['success']:
        return jsonify(result)
    else:
        # Failed upgrade - format errors for display
        errors = [{
            'file': 'Full Asset',
            'error': result['error'],
            'traceback': result['traceback']
        }]
        
        return jsonify({
            'success': False,
            'partial_success': False,
            'asset_id': result.get('asset_id'),
            'asset_name': result.get('asset_name'),
            'created': result.get('created'),
            'upgraded_files': [],
            'unchanged_files': [],
            'failed_files': ['Full Asset'],
            'errors': errors
        })


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
