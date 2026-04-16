from supabase import create_client

url = "https://zsjmzxahxmedeufrdecf.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpzam16eGFoeG1lZGV1ZnJkZWNmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjIzOTE4NSwiZXhwIjoyMDkxODE1MTg1fQ.kVrZU8CeB3hPufv1gWghYZRLOFTlXQo4ONM00DcS1yM"

supabase = create_client(url,key)