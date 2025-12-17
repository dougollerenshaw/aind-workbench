import json
import os
from flask import Flask, render_template_string, request, jsonify
from aind_data_access_api.document_db import MetadataDbClient
import pandas as pd
import json5

app = Flask(__name__)

# Initialize the MongoDB client
client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

HOST = os.getenv("QUERY_TOOL_HOST", "0.0.0.0")
PORT = int(os.getenv("QUERY_TOOL_PORT", "5000"))
DEFAULT_LIMIT = int(os.getenv("QUERY_TOOL_DEFAULT_LIMIT", "100"))

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'template.html')

@app.route('/')
def index():
    # Load template fresh on each request so changes are picked up
    with open(TEMPLATE_PATH, 'r') as f:
        html_template = f.read()
    return render_template_string(html_template)

@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.json
        pipeline_str = data.get('pipeline', '[]')

        # Parse the pipeline; allow relaxed JSON (JSON5) for Mongo-style input
        try:
            parsed = json.loads(pipeline_str)
        except json.JSONDecodeError:
            parsed = json5.loads(pipeline_str)

        default_limit_applied = False
        if isinstance(parsed, dict):
            # Accept MongoDB "find by example" documents by wrapping into a pipeline
            pipeline = [{"$match": parsed}, {"$limit": DEFAULT_LIMIT}]
            default_limit_applied = True
        elif isinstance(parsed, list):
            pipeline = parsed
        else:
            return jsonify({"error": "Pipeline must be a JSON array or object"}), 400
        
        # Run the query
        results = client.aggregate_docdb_records(pipeline)
        
        # Try to create table/markdown views
        table_html = None
        markdown = None
        
        try:
            if results and isinstance(results, list) and len(results) > 0:
                df = pd.DataFrame(results)
                # Clean up date columns if they exist
                for col in df.columns:
                    if 'date' in col.lower() and df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str[:19]  # Truncate to datetime
                
                table_html = df.to_html(index=False, classes='dataframe')
                markdown = df.to_markdown(index=False)
        except Exception as e:
            # If DataFrame creation fails, that's okay
            pass
        
        return jsonify({
            'results': results,
            'count': len(results) if isinstance(results, list) else 0,
            'default_limit_applied': default_limit_applied,
            'default_limit': DEFAULT_LIMIT if default_limit_applied else None,
            'table_html': table_html,
            'markdown': markdown
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)