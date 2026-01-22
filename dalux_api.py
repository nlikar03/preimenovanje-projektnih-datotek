import requests
import json
from typing import Dict, List, Optional, Tuple
import io


class DaluxAPIClient:
    def __init__(self, api_key: str, base_url: str = "https://node2.field.dalux.com/service/api"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "X-API-KEY": api_key,
            "Accept": "application/json"
        }
    
    def get_all_projects(self) -> List[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/5.1/projects",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.RequestException as e:
            raise Exception(f"Failed to get projects: {str(e)}")
    
    def find_project_by_number(self, project_number: str) -> Optional[Dict]:
        projects = self.get_all_projects()
        
        for project in projects:
            # The API returns a list of objects where the actual info is inside a 'data' key
            inner_data = project.get("data", {})
            
            # Check if 'number' exists and matches
            # Using .strip() helps if there are hidden spaces in the project number
            if str(inner_data.get("number")).strip() == str(project_number).strip():
                return inner_data
        
        return None
    
    def get_file_areas(self, project_id: str) -> List[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/5.1/projects/{project_id}/file_areas",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.RequestException as e:
            raise Exception(f"Failed to get file areas: {str(e)}")
    
    def get_folders(self, project_id: str, file_area_id: str) -> List[Dict]:
        try:
            response = requests.get(
                f"{self.base_url}/5.1/projects/{project_id}/file_areas/{file_area_id}/folders",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.RequestException as e:
            raise Exception(f"Failed to get folders: {str(e)}")
    
    def get_folder_by_path(self, project_id: str, file_area_id: str, folder_path: str) -> Optional[Dict]:
        folders = self.get_folders(project_id, file_area_id)
        

        target_name = folder_path.split('/')[-1]

        for folder in folders:
            folder_data = folder.get("data", {})
            # LOOK HERE: We changed "name" to "folderName"
            if folder_data.get("folderName") == target_name:
                return folder_data
                
        return None
    
    def create_upload_slot(self, project_id: str, file_area_id: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/1.0/projects/{project_id}/file_areas/{file_area_id}/upload",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["data"]["uploadGuid"]
        except requests.RequestException as e:
            raise Exception(f"Failed to create upload slot: {str(e)}")
    
    def upload_file_content(self, project_id: str, file_area_id: str, 
                           upload_guid: str, file_content: bytes, 
                           filename: str) -> bool:

        try:
            file_size = len(file_content)
            

            response = requests.post(
                f"{self.base_url}/1.0/projects/{project_id}/file_areas/{file_area_id}/upload/{upload_guid}",
                headers={
                    **self.headers,
                    "Content-Disposition": f'form-data; filename="{filename}"',
                    "Content-Range": f"bytes 0-{file_size-1}/{file_size}",
                    "Content-Type": "application/octet-stream"
                },
                data=file_content,
                timeout=60
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            raise Exception(f"Failed to upload file content: {str(e)}")
    
    def finalize_upload(self, project_id: str, file_area_id: str, 
                       upload_guid: str, filename: str, 
                       folder_id: str, file_type: str = "document") -> Dict:

        try:
            response = requests.post(
                f"{self.base_url}/2.0/projects/{project_id}/file_areas/{file_area_id}/upload/{upload_guid}/finalize",
                headers={
                    **self.headers,
                    "Content-Type": "application/json"
                },
                json={
                    "fileName": filename,
                    "fileType": file_type,
                    "folderId": folder_id
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to finalize upload: {str(e)}")
    
    def upload_complete_file(self, project_id: str, file_area_id: str,
                            folder_id: str, filename: str, 
                            file_content: bytes) -> Dict:

        # Step 1: Create upload slot
        upload_guid = self.create_upload_slot(project_id, file_area_id)
        
        # Step 2: Upload content
        self.upload_file_content(project_id, file_area_id, upload_guid, 
                                file_content, filename)
        
        # Step 3: Finalize
        result = self.finalize_upload(project_id, file_area_id, upload_guid, 
                                      filename, folder_id)
        
        return result
    
    def get_or_create_folder(self, project_id: str, file_area_id: str,
                            folder_path: str) -> str:

        folder = self.get_folder_by_path(project_id, file_area_id, folder_path)
        
        if folder:
            return folder.get("folderId")
        

        raise Exception(f"Folder not found: {folder_path}. Please create it manually in Dalux.")


class DaluxUploadManager:

    def __init__(self, api_key: str):
        self.client = DaluxAPIClient(api_key)
        self.project_cache = {}
    
    def setup_project(self, project_number: str) -> Tuple[str, str]:

        project = self.client.find_project_by_number(project_number)
        if not project:
            raise Exception(f"Project not found with number: {project_number}")
        
        project_id = project["projectId"]
        
        file_areas = self.client.get_file_areas(project_id)
        if not file_areas:
            raise Exception(f"No file areas found for project {project_number}")
        
        file_area_id = file_areas[0]["data"]["fileAreaId"]
        
        self.project_cache[project_number] = {
            "project_id": project_id,
            "file_area_id": file_area_id,
            "project_name": project["projectName"]
        }
        
        return project_id, file_area_id
    
    def upload_file_to_folder(self, project_number: str, folder_path: str,
                             filename: str, file_content: bytes) -> Dict:

        if project_number not in self.project_cache:
            self.setup_project(project_number)
        
        cache = self.project_cache[project_number]
        project_id = cache["project_id"]
        file_area_id = cache["file_area_id"]
        
        folder_id = self.client.get_or_create_folder(
            project_id, file_area_id, folder_path
        )
        
        result = self.client.upload_complete_file(
            project_id, file_area_id, folder_id, filename, file_content
        )
        
        return result
    
    def bulk_upload_from_structure(self, project_number: str, 
                                   files_dict: Dict[str, List[Tuple[str, bytes]]]) -> Dict:
        
        results = {
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        if project_number not in self.project_cache:
            self.setup_project(project_number)
        
        for folder_path, files in files_dict.items():
            for filename, file_content in files:
                try:
                    result = self.upload_file_to_folder(
                        project_number, folder_path, filename, file_content
                    )
                    results["success"] += 1
                    results["details"].append({
                        "file": filename,
                        "folder": folder_path,
                        "status": "success",
                        "result": result
                    })
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "file": filename,
                        "folder": folder_path,
                        "status": "failed",
                        "error": str(e)
                    })
        
        return results

