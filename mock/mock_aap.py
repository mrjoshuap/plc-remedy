"""Mock Ansible Automation Platform API server for testing."""
from flask import Flask, request, jsonify
import random
import time
from datetime import datetime

app = Flask(__name__)

# In-memory job storage
_jobs = {}
_job_counter = 1000


@app.route('/api/v2/job_templates/<int:template_id>/launch/', methods=['POST'])
def launch_job(template_id):
    """Launch a mock job template."""
    global _job_counter
    
    job_id = _job_counter
    _job_counter += 1
    
    # Create job record
    job = {
        'id': job_id,
        'status': 'pending',
        'job_template': template_id,
        'created': datetime.now().isoformat(),
        'extra_vars': request.json.get('extra_vars', {}) if request.is_json else {}
    }
    
    _jobs[job_id] = job
    
    return jsonify({
        'id': job_id,
        'status': 'pending',
        'url': f'/api/v2/jobs/{job_id}/',
        'job_template': template_id
    }), 201


@app.route('/api/v2/jobs/<int:job_id>/', methods=['GET'])
def get_job(job_id):
    """Get job status."""
    if job_id not in _jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = _jobs[job_id]
    
    # Simulate job progression
    if job['status'] == 'pending':
        # Randomly move to running after some time
        if random.random() < 0.3:
            job['status'] = 'running'
            job['started'] = datetime.now().isoformat()
    elif job['status'] == 'running':
        # Randomly complete
        if random.random() < 0.2:
            if random.random() < 0.1:  # 10% failure rate
                job['status'] = 'failed'
            else:
                job['status'] = 'successful'
            job['finished'] = datetime.now().isoformat()
    
    return jsonify({
        'id': job_id,
        'status': job['status'],
        'finished': job.get('finished') is not None,
        'failed': job['status'] == 'failed',
        'elapsed': random.randint(5, 30) if job['status'] != 'pending' else 0,
        'job_template': job['job_template']
    })


@app.route('/api/v2/jobs/<int:job_id>/stdout/', methods=['GET'])
def get_job_stdout(job_id):
    """Get job stdout output."""
    if job_id not in _jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = _jobs[job_id]
    
    output = f"""Mock AAP Job Output (Job ID: {job_id})
========================================
PLAY [Remediation Task] ****************

TASK [Execute remediation action] ******
ok: [localhost]

PLAY RECAP *****************************
localhost                  : ok=1    changed=0    unreachable=0    failed=0
"""
    
    return output, 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    print("Starting Mock AAP API server on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
