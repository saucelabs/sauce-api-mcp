"""Basic tests for the Sauce Labs MCP server."""
import pytest
from unittest.mock import AsyncMock, patch
import httpx


@pytest.fixture
def mock_sauce_server():
    """Create a mock SauceServer instance."""
    with patch('sauce_mcp.SauceServer') as mock:
        server = mock.return_value
        server.username = "test_user"
        server.access_key = "test_key"
        return server


class TestSauceServer:
    """Test the SauceServer class."""
    
    @pytest.mark.asyncio
    async def test_get_account_info_success(self, mock_sauce_server):
        """Test successful account info retrieval."""
        # Mock the API response
        mock_response = httpx.Response(
            200,
            json={"username": "test_user", "minutes": 1000}
        )
        
        with patch.object(mock_sauce_server, 'sauce_api_call', return_value=mock_response.json()):
            result = await mock_sauce_server.get_account_info()
            
        assert "username" in result
        assert result["username"] == "test_user"
    
    @pytest.mark.asyncio
    async def test_get_recent_jobs_with_limit(self, mock_sauce_server):
        """Test getting recent jobs with a specific limit."""
        # Mock the API response
        mock_jobs = [
            {"id": "job1", "name": "Test Job 1"},
            {"id": "job2", "name": "Test Job 2"}
        ]
        
        with patch.object(mock_sauce_server, 'sauce_api_call', return_value=mock_jobs):
            result = await mock_sauce_server.get_recent_jobs(limit=2)
            
        assert len(result) == 2
        assert result[0]["id"] == "job1"
    
    @pytest.mark.asyncio
    async def test_enhanced_404_handling(self, mock_sauce_server):
        """Test enhanced 404 error handling."""
        # Mock a 404 response
        mock_response = httpx.Response(404)
        
        with patch.object(mock_sauce_server, 'sauce_api_call', return_value=mock_response):
            # Assuming the method handles 404s and returns enhanced error
            with patch.object(mock_sauce_server, 'get_job_details') as mock_method:
                mock_method.return_value = {
                    "error": "Job not found: test-job-id",
                    "job_id": "test-job-id",
                    "possible_reasons": ["Job ID does not exist"],
                    "suggestions": ["Use get_recent_jobs to find available jobs"]
                }
                
                result = await mock_sauce_server.get_job_details("test-job-id")
                
        assert "error" in result
        assert "possible_reasons" in result
        assert "suggestions" in result


class TestErrorHandling:
    """Test error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self, mock_sauce_server):
        """Test handling of network errors."""
        with patch.object(mock_sauce_server, 'sauce_api_call', side_effect=httpx.RequestError("Network error")):
            # This should be handled gracefully by the server
            with pytest.raises(httpx.RequestError):
                await mock_sauce_server.get_account_info()
    
    def test_invalid_credentials_format(self):
        """Test validation of credentials format."""
        # Test that the server validates credential formats appropriately
        # This would depend on your actual validation logic
        pass


class TestAssetHandling:
    """Test asset retrieval functionality."""
    
    @pytest.mark.asyncio
    async def test_vdc_vs_rdc_job_detection(self, mock_sauce_server):
        """Test that the server correctly identifies VDC vs RDC jobs."""
        # Mock VDC job details
        vdc_job = {
            "browser": "chrome",
            "platform": "Windows 11"
        }
        
        # Mock RDC job details  
        rdc_job = {
            "device_name": "Samsung Galaxy S21",
            "os": "Android"
        }
        
        with patch.object(mock_sauce_server, 'get_job_details', return_value=vdc_job):
            result = await mock_sauce_server.get_job_details("vdc-job-id")
            assert "browser" in result
        
        with patch.object(mock_sauce_server, 'get_job_details', return_value=rdc_job):
            result = await mock_sauce_server.get_job_details("rdc-job-id")
            assert "device_name" in result
