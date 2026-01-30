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
        /* Tree view styles (from query tool) */
        .tree-node, .tree-leaf {
            font-family: monospace;
            font-size: 12px;
        }
        .tree-children {
            padding-left: 24px;
        }
        details summary {
            color: #000;
            cursor: pointer;
            user-select: none;
        }
        .tree-leaf {
            color: #000;
            padding: 2px 0;
        }
        .tree-leaf .value {
            color: #10b981;
        }
        .json-container {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            max-height: 600px;
            overflow-y: auto;
            font-family: monospace;
        }
        .comparison-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 10px;
        }
        .button-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .share-btn {
            background-color: #28a745;
        }
        .share-btn:hover {
            background-color: #218838;
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
        
        <div class="button-group">
            <button id="checkBtn" onclick="checkUpgrade()" disabled>Check Upgrade</button>
            <button id="shareBtn" onclick="copyShareLink()" class="share-btn" disabled>Copy Shareable URL</button>
        </div>
        
        <div id="results"></div>
    </div>

    <script>
        // Tree view helper functions (from query tool)
        function isObject(value) {
            return value !== null && typeof value === 'object' && !Array.isArray(value);
        }

        function formatScalar(value) {
            if (typeof value === 'string') return '"' + value + '"';
            if (value === null) return 'null';
            return String(value);
        }

        function buildTreeNode(value, label, depth) {
            if (typeof depth === 'undefined') depth = 0;
            if (Array.isArray(value) || isObject(value)) {
                var details = document.createElement('details');
                // Collapse all by default
                details.open = false;
                var summary = document.createElement('summary');
                summary.textContent = label;
                details.appendChild(summary);

                var children = document.createElement('div');
                children.className = 'tree-children';

                if (Array.isArray(value)) {
                    for (var idx = 0; idx < value.length; idx++) {
                        children.appendChild(buildTreeNode(value[idx], '[' + idx + ']', depth + 1));
                    }
                } else {
                    var entries = Object.entries(value);
                    for (var i = 0; i < entries.length; i++) {
                        var k = entries[i][0];
                        var v = entries[i][1];
                        children.appendChild(buildTreeNode(v, k, depth + 1));
                    }
                }

                details.appendChild(children);
                return details;
            }

            var leaf = document.createElement('div');
            leaf.className = 'tree-leaf';
            var labelSpan = document.createElement('span');
            labelSpan.textContent = label + ': ';
            var valueSpan = document.createElement('span');
            valueSpan.className = 'value';
            valueSpan.textContent = formatScalar(value);
            leaf.appendChild(labelSpan);
            leaf.appendChild(valueSpan);
            return leaf;
        }

        function renderJsonTree(containerId, data) {
            var container = document.getElementById(containerId);
            container.innerHTML = '';
            if (data === null || data === undefined) {
                container.textContent = 'No data.';
                return;
            }
            
            // Build tree starting from root
            var entries = Object.entries(data);
            for (var i = 0; i < entries.length; i++) {
                var k = entries[i][0];
                var v = entries[i][1];
                container.appendChild(buildTreeNode(v, k, 0));
            }
        }

        function checkUpgrade() {
            const assetId = document.getElementById('assetId').value.trim();
            const resultsDiv = document.getElementById('results');
            
            if (!assetId) {
                resultsDiv.innerHTML = '<div class="error">Please enter an asset ID or name</div>';
                document.getElementById('shareBtn').disabled = true;
                return;
            }
            
            // Update the browser URL
            const newUrl = window.location.pathname + '?asset_id=' + encodeURIComponent(assetId);
            window.history.pushState({asset_id: assetId}, '', newUrl);
            
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
                    // Disable share button on error
                    document.getElementById('shareBtn').disabled = true;
                } else {
                    displayResults(data);
                }
            })
            .catch(error => {
                resultsDiv.innerHTML = `<div class="error"><strong>Error:</strong> ${error.message}</div>`;
                // Disable share button on error
                document.getElementById('shareBtn').disabled = true;
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
            
            // Upgrade result summary
            if (data.success) {
                html += '<div class="success">';
                html += '<h3>All Fields Upgraded Successfully!</h3>';
                html += '<p>This asset can be fully upgraded to schema v2.</p>';
                html += '</div>';
            } else if (data.partial_success) {
                html += '<div class="error">';
                html += '<h3>Partial Upgrade Success</h3>';
                html += `<p>${data.successful_fields.length} fields upgraded successfully, ${data.failed_fields.length} fields failed.</p>`;
                html += '</div>';
            } else {
                html += '<div class="error">';
                html += '<h3>Upgrade Failed</h3>';
                html += '<p>The full asset could not be upgraded.</p>';
                if (data.overall_error) {
                    // Format error with proper line breaks
                    const errorText = String(data.overall_error || '');
                    const nl = String.fromCharCode(10);
                    const formattedError = errorText.split(nl).join('<br>');
                    html += '<div style="margin-top: 10px;"><strong>Error:</strong><br><div style="margin-top: 5px; white-space: pre-wrap; font-family: monospace; font-size: 12px;">' + formattedError + '</div></div>';
                    if (data.overall_traceback) {
                        html += '<details style="margin-top: 10px;"><summary style="cursor: pointer; font-weight: bold;">Show Full Traceback</summary>';
                        html += '<pre style="font-size: 12px; overflow-x: auto; background: #f8f9fa; padding: 10px; border-radius: 4px;">' + data.overall_traceback + '</pre>';
                        html += '</details>';
                    }
                }
                html += '</div>';
            }
            
            // Show per-field results
            if (data.field_results) {
                html += '<details open style="margin-top: 20px;"><summary style="cursor: pointer; font-weight: bold; font-size: 16px;">Field-by-Field View</summary>';
                html += '<div style="margin-top: 10px;">';
                
                // Iterate through each field
                Object.keys(data.field_results).sort().forEach(fieldName => {
                    const fieldResult = data.field_results[fieldName];
                    
                    html += '<details open style="margin: 15px 0; border: 1px solid #ddd; border-radius: 4px; padding: 10px;">';
                    if (fieldResult.success === true) {
                        let displayName = fieldName;
                        if (fieldResult.converted_to) {
                            displayName += ` → ${fieldResult.converted_to}`;
                        }
                        html += `<summary style="cursor: pointer; font-weight: bold; color: #155724; background: #d4edda; padding: 8px; border-radius: 4px;">[SUCCESS] ${displayName}</summary>`;
                    } else if (fieldResult.success === false) {
                        html += `<summary style="cursor: pointer; font-weight: bold; color: #721c24; background: #f8d7da; padding: 8px; border-radius: 4px;">[FAILED] ${fieldName}</summary>`;
                    } else {
                        // success === null, dependency issue or info
                        html += `<summary style="cursor: pointer; font-weight: bold; color: #0c5460; background: #d1ecf1; padding: 8px; border-radius: 4px;">[DEPENDENCY] ${fieldName}</summary>`;
                    }
                    
                    html += '<div style="margin-top: 10px;">';
                    
                    if (fieldResult.success === true) {
                        // Show side-by-side comparison for successful upgrades
                        html += '<div class="comparison-grid">';
                        html += '<div>';
                        html += '<h4 style="margin-top: 0;">Original (v1)</h4>';
                        html += `<div id="${fieldName}-original-tree" class="json-container"></div>`;
                        html += '</div>';
                        html += '<div>';
                        let upgradedLabel = 'Upgraded (v2)';
                        if (fieldResult.converted_to) {
                            upgradedLabel += ` - ${fieldResult.converted_to}`;
                        }
                        html += `<h4 style="margin-top: 0;">${upgradedLabel}</h4>`;
                        html += `<div id="${fieldName}-upgraded-tree" class="json-container"></div>`;
                        html += '</div>';
                        html += '</div>';
                    } else if (fieldResult.success === false) {
                        // Show error for failed fields
                        html += '<div class="error" style="margin-bottom: 10px;">';
                        // Format error with proper line breaks
                        const errorText = String(fieldResult.error || '');
                        const nl = String.fromCharCode(10);
                        const formattedFieldError = errorText.split(nl).join('<br>');
                        html += `<strong>Error:</strong><br><div style="margin-top: 5px; white-space: pre-wrap; font-family: monospace; font-size: 12px;">${formattedFieldError}</div>`;
                        if (fieldResult.traceback) {
                            html += '<details style="margin-top: 10px;"><summary style="cursor: pointer; font-weight: bold;">Show Full Traceback</summary>';
                            html += `<pre style="font-size: 12px; overflow-x: auto; background: #f8f9fa; padding: 10px; border-radius: 4px;">${fieldResult.traceback}</pre>`;
                            html += '</details>';
                        }
                        html += '</div>';
                        
                        // Show original data for failed fields
                        html += '<div>';
                        html += '<h4 style="margin-top: 0;">Original (v1)</h4>';
                        html += `<div id="${fieldName}-failed-tree" class="json-container"></div>`;
                        html += '</div>';
                    } else {
                        // success === null, show info message and original data
                        if (fieldResult.info) {
                            html += '<div style="margin-bottom: 10px; padding: 10px; background: #f8f9fa; border-radius: 4px;">';
                            html += `<strong>Note:</strong> ${fieldResult.info}`;
                            html += '</div>';
                        }
                        
                        // Show original data
                        html += '<div>';
                        html += '<h4 style="margin-top: 0;">Original (v1)</h4>';
                        html += `<div id="${fieldName}-info-tree" class="json-container"></div>`;
                        html += '</div>';
                    }
                    
                    html += '</div>';
                    html += '</details>';
                });
                
                html += '</div>';
                html += '</details>';
            }
            
            resultsDiv.innerHTML = html;
            
            // Enable the share button now that we have valid results
            document.getElementById('shareBtn').disabled = false;
            
            // Render JSON trees for each field
            if (data.field_results) {
                Object.keys(data.field_results).forEach(fieldName => {
                    const fieldResult = data.field_results[fieldName];
                    if (fieldResult.success === true) {
                        renderJsonTree(`${fieldName}-original-tree`, fieldResult.original);
                        renderJsonTree(`${fieldName}-upgraded-tree`, fieldResult.upgraded);
                    } else if (fieldResult.success === false) {
                        renderJsonTree(`${fieldName}-failed-tree`, fieldResult.original);
                    } else {
                        // success === null (info only)
                        renderJsonTree(`${fieldName}-info-tree`, fieldResult.original);
                    }
                });
            }
        }
        
        // Enable/disable Check Upgrade button based on input
        document.getElementById('assetId').addEventListener('input', function(e) {
            const assetId = e.target.value.trim();
            document.getElementById('checkBtn').disabled = !assetId;
        });
        
        // Allow Enter key to trigger check
        document.getElementById('assetId').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                checkUpgrade();
            }
        });
        
        // Copy current URL to clipboard
        function copyShareLink() {
            const currentUrl = window.location.href;
            const nl = String.fromCharCode(10);
            
            // Try modern clipboard API first
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(currentUrl).then(function() {
                    alert('Copied to clipboard:' + nl + nl + currentUrl);
                }).catch(function(err) {
                    // Fall back to manual selection method
                    fallbackCopy(currentUrl);
                });
            } else {
                // Fall back for older browsers
                fallbackCopy(currentUrl);
            }
        }
        
        function fallbackCopy(text) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            const nl = String.fromCharCode(10);
            try {
                document.execCommand('copy');
                alert('Copied to clipboard:' + nl + nl + text);
            } catch (err) {
                alert('Failed to copy URL. Please copy manually:' + nl + nl + text);
            }
            document.body.removeChild(textArea);
        }
        
        // Parse URL parameters on page load
        function getUrlParams() {
            const params = {};
            const search = window.location.search.substring(1);
            if (search) {
                const pairs = search.split('&');
                for (let i = 0; i < pairs.length; i++) {
                    const pair = pairs[i].split('=');
                    params[decodeURIComponent(pair[0])] = decodeURIComponent(pair[1] || '');
                }
            }
            return params;
        }
        
        // Auto-load asset from URL if present
        document.addEventListener('DOMContentLoaded', function() {
            const params = getUrlParams();
            if (params.asset_id) {
                document.getElementById('assetId').value = params.asset_id;
                // Enable the Check Upgrade button since we have text
                document.getElementById('checkBtn').disabled = false;
                // Auto-run the upgrade
                checkUpgrade();
            }
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/check_upgrade", methods=["POST"])
def check_upgrade():
    """Check if an asset can be upgraded"""
    data = request.json
    asset_identifier = data.get("asset_id", "").strip()

    if not asset_identifier:
        return jsonify({"error": "Asset ID or name is required"}), 400

    print(f"\n{'='*60}")
    print(f"Checking upgrade for: {asset_identifier}")
    print(f"{'='*60}")

    # Call the standalone upgrade function (field-by-field approach)
    result = upgrade_asset(asset_identifier)

    if "error" in result and "field_results" not in result:
        # Asset not found error
        return jsonify(result), 404

    # Return the per-field results
    return jsonify(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIND Metadata Upgrader Tool")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5001, help="Port to bind to (default: 5001)")

    args = parser.parse_args()

    print(f"Starting AIND Metadata Upgrader Tool on {args.host}:{args.port}")
    print(f"Access at: http://localhost:{args.port}")

    app.run(host=args.host, port=args.port, debug=True)
