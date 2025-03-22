from flask import Flask, render_template, request, jsonify
import subprocess
import os
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    try:
        # Get username from form or use default
        username = request.form.get('username', 'bharani')
        
        # Change to the Modal repository directory
        os.chdir('/app/Modal')
        
        # Set environment variables
        env = os.environ.copy()
        env['MODAL_APP_NAME'] = username
        
        # Run the deployment command
        result = subprocess.run(
            ['modal', 'deploy', 'modal_container.py'],
            capture_output=True,
            text=True,
            env=env
        )
        
        app.logger.info(f"Deployment stdout: {result.stdout}")
        app.logger.info(f"Deployment stderr: {result.stderr}")
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'Deployment successful',
                'details': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Deployment failed',
                'details': result.stderr
            })
    
    except Exception as e:
        app.logger.error(f"Error during deployment: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
