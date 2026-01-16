"""Ansible Automation Platform (AAP) API client."""
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import AAPConfig

logger = logging.getLogger(__name__)


class AAPClient:
    """Client for interacting with Ansible Automation Platform API."""
    
    def __init__(self, config: AAPConfig):
        """Initialize AAP client.
        
        Args:
            config: AAP configuration
        """
        self.config = config
        self._session = requests.Session()
        
        # Configure connection pooling and retry strategy
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=0.3,  # Wait 0.3, 0.6, 1.2 seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
            allowed_methods=["GET", "POST"]  # Only retry safe methods
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,  # Number of connection pools to cache
            pool_maxsize=10,  # Maximum number of connections to save in the pool
            pool_block=False  # Don't block if pool is full, raise exception instead
        )
        
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        
        if not config.mock_mode:
            # Set up authentication for real AAP
            if config.token:
                self._session.headers.update({
                    'Authorization': f'Bearer {config.token}'
                })
            self._session.headers.update({
                'Content-Type': 'application/json'
            })
    
    def launch_job(self, job_template_id: int, extra_vars: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Launch an AAP job template.
        
        Args:
            job_template_id: ID of the job template to launch
            extra_vars: Optional extra variables to pass to the job
            
        Returns:
            Dictionary with job_id and status, or error information
            
        Raises:
            RuntimeError: If job launch fails
        """
        # Use HTTP requests if base_url is configured (even in mock_mode for mock server)
        # Only use local simulation if no base_url is set
        if self.config.base_url:
            return self._launch_real_job(job_template_id, extra_vars)
        else:
            return self._launch_mock_job(job_template_id, extra_vars)
    
    def _launch_real_job(self, job_template_id: int, extra_vars: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Launch a real AAP job.
        
        Args:
            job_template_id: ID of the job template
            extra_vars: Optional extra variables
            
        Returns:
            Dictionary with job information
        """
        url = f"{self.config.base_url}/api/v2/job_templates/{job_template_id}/launch/"
        
        payload = {}
        if extra_vars:
            payload['extra_vars'] = extra_vars
        
        try:
            response = self._session.post(
                url,
                json=payload,
                verify=self.config.verify_ssl,
                timeout=30
            )
            response.raise_for_status()
            
            job_data = response.json()
            logger.info(f"Launched AAP job template {job_template_id}, job ID: {job_data.get('id')}")
            
            return {
                'success': True,
                'job_id': job_data.get('id'),
                'status': job_data.get('status', 'pending'),
                'url': job_data.get('url', '')
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"AAP API error launching job template {job_template_id}: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _launch_mock_job(self, job_template_id: int, extra_vars: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Launch a mock AAP job (for testing).
        
        Args:
            job_template_id: ID of the job template
            extra_vars: Optional extra variables
            
        Returns:
            Dictionary with mock job information
        """
        # Generate a realistic job ID
        job_id = int(time.time() * 1000) % 1000000  # 6-digit job ID
        
        logger.info(f"Mock: Launched AAP job template {job_template_id}, mock job ID: {job_id}")
        
        return {
            'success': True,
            'job_id': job_id,
            'status': 'pending',
            'url': f"/api/v2/jobs/{job_id}/"
        }
    
    def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get status of an AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Dictionary with job status information
        """
        # Use HTTP requests if base_url is configured (even in mock_mode for mock server)
        # Only use local simulation if no base_url is set
        if self.config.base_url:
            return self._get_real_job_status(job_id)
        else:
            return self._get_mock_job_status(job_id)
    
    def _get_real_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get status of a real AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Dictionary with job status
        """
        url = f"{self.config.base_url}/api/v2/jobs/{job_id}/"
        
        try:
            response = self._session.get(
                url,
                verify=self.config.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            
            job_data = response.json()
            
            return {
                'success': True,
                'job_id': job_id,
                'status': job_data.get('status', 'unknown'),
                'finished': job_data.get('finished', False),
                'failed': job_data.get('failed', False),
                'elapsed': job_data.get('elapsed', 0)
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"AAP API error getting job status {job_id}: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'job_id': job_id,
                'status': 'error',
                'error': str(e)
            }
    
    def _get_mock_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get status of a mock AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Dictionary with mock job status
        """
        # Simulate job progression: pending -> running -> successful
        # Use job_id as seed for deterministic behavior
        seed = job_id % 1000
        elapsed = int(time.time()) % 60  # Simulate elapsed time
        
        # Simple state machine based on elapsed time
        if elapsed < 5:
            status = 'pending'
            finished = False
        elif elapsed < 15:
            status = 'running'
            finished = False
        else:
            status = 'successful'
            finished = True
        
        # Occasionally simulate failures (5% chance)
        if seed < 50:
            status = 'failed'
            finished = True
        
        return {
            'success': True,
            'job_id': job_id,
            'status': status,
            'finished': finished,
            'failed': (status == 'failed'),
            'elapsed': elapsed
        }
    
    def get_job_output(self, job_id: int) -> str:
        """Get stdout output from an AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Job output as string
        """
        # Use HTTP requests if base_url is configured (even in mock_mode for mock server)
        # Only use local simulation if no base_url is set
        if self.config.base_url:
            return self._get_real_job_output(job_id)
        else:
            return self._get_mock_job_output(job_id)
    
    def _get_real_job_output(self, job_id: int) -> str:
        """Get stdout output from a real AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Job output as string
        """
        url = f"{self.config.base_url}/api/v2/jobs/{job_id}/stdout/"
        
        try:
            response = self._session.get(
                url,
                verify=self.config.verify_ssl,
                timeout=10,
                params={'format': 'txt'}
            )
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            error_msg = f"AAP API error getting job output {job_id}: {str(e)}"
            logger.error(error_msg)
            return f"Error retrieving job output: {str(e)}"
    
    def _get_mock_job_output(self, job_id: int) -> str:
        """Get stdout output from a mock AAP job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Mock job output
        """
        return f"""Mock AAP Job Output (Job ID: {job_id})
========================================
PLAY [Remediation Task] ****************

TASK [Execute remediation action] ******
ok: [localhost]

PLAY RECAP *****************************
localhost                  : ok=1    changed=0    unreachable=0    failed=0
"""
    
    def poll_job_until_complete(self, job_id: int, timeout: int = 300, poll_interval: int = 2) -> Dict[str, Any]:
        """Poll job status until it completes or times out.
        
        Args:
            job_id: ID of the job
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds
            
        Returns:
            Final job status dictionary
        """
        start_time = time.time()
        
        while True:
            status = self.get_job_status(job_id)
            
            if not status.get('success'):
                return status
            
            if status.get('finished', False):
                logger.info(f"Job {job_id} completed with status: {status.get('status')}")
                return status
            
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Job {job_id} polling timed out after {timeout} seconds")
                return {
                    'success': False,
                    'job_id': job_id,
                    'status': 'timeout',
                    'error': f'Job did not complete within {timeout} seconds'
                }
            
            time.sleep(poll_interval)
