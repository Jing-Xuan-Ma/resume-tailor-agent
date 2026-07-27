import requests

# 1. Upload resume (txt)
url = 'http://127.0.0.1:8000/api/v1/resume-tailor/upload-resume'
body = {
    'user_id': '00000000-0000-0000-0000-000000000001',
    'resume_text': open('test_resume.txt', encoding='utf-8').read()
}
r = requests.post(url, json=body)
print('=== Upload Resume ===')
print('Status:', r.status_code)
print('Resp:', r.json())

# 2. Parse JD
jd = '''Senior Software Engineer
We are looking for a Senior Software Engineer to join our team.
Responsibilities:
- Design and implement RESTful APIs
- Optimize system performance and reduce latency
- Lead engineering teams and mentor junior developers
- Work with React frontend and Python backend
Requirements:
- 5+ years experience in software engineering
- Strong knowledge of Python, FastAPI, or similar frameworks
- Experience with React, TypeScript, PostgreSQL, Docker
- Experience with microservices architecture
- Strong leadership and communication skills
Preferred:
- Experience with cloud services (AWS/GCP)
- CI/CD pipeline experience'''
r2 = requests.post('http://127.0.0.1:8000/api/v1/resume-tailor/parse-jd', json={'jd_text': jd})
print()
print('=== Parse JD ===')
print('Status:', r2.status_code)
jd_parsed = r2.json()
print('Skills:', jd_parsed.get('parsed',{}).get('required_skills',[]))

# 3. Tailor
r3 = requests.post('http://127.0.0.1:8000/api/v1/resume-tailor/tailor', json={
    'user_id': '00000000-0000-0000-0000-000000000001',
    'resume_id': '00000000-0000-0000-0000-000000000002',
    'jd_text': jd
})
print()
print('=== Tailor ===')
print('Status:', r3.status_code)
result = r3.json()
print('Success:', result.get('success'))
tr = result.get('tailored_resume', {})
print('Has experiences:', len(tr.get('experiences', [])))
print('Has skills:', len(tr.get('skills', [])))
print('Has projects:', len(tr.get('projects', [])))
print('Has education:', len(tr.get('education', [])))
print('ATS score:', tr.get('ats_score_estimate'))
print('Tailoring summary:', (tr.get('tailoring_summary', '') or '')[:200])
if tr.get('experiences'):
    for exp in tr['experiences']:
        print(f'  Exp: {exp["title"]} at {exp["company"]} ({exp["date_range"]})')
        for b in exp['bullets']:
            print(f'    - {b["text"][:80]}')
