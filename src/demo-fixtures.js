// 실제 data/overlap/gongchae_all.json과 roles.json에서 추출한 화면 검수용 샘플입니다.
// 제출용 공고 API가 연결되면 services.js가 이 fixture 대신 API 응답을 사용합니다.
export const DEMO_POSTINGS = [
  { postingId:"role-238",externalId:"177147",companyName:"펄어비스",positionTitle:"[인턴십] QA Beginner 인턴십 모집",jobFamily:"생산/품질",employmentType:"기간제·인턴",companyType:"중견기업",deadline:"2026-09-18",sourceUrl:"https://www.pearlabyss.com/ko-KR/Company/Careers/detail?_jobOpeningNo=842",coachReady:true,requiredSkills:["Azure"] },
  { postingId:"role-148",externalId:"176849",companyName:"케이피에프",positionTitle:"화스너생산팀 신입 모집",jobFamily:"생산/품질",employmentType:"정규직",companyType:"중견기업",deadline:"2026-09-18",sourceUrl:"https://kpf.recruiter.co.kr/career/jobs/126948",coachReady:true,requiredSkills:["엑셀"] },
  { postingId:"role-387",externalId:"177708",companyName:"케이피에프",positionTitle:"부품영업팀 신입 또는 경력 모집",jobFamily:"영업/마케팅",employmentType:"정규직",companyType:"중견기업",deadline:"2026-09-18",sourceUrl:"https://kpf.recruiter.co.kr/career/jobs/127452",coachReady:true,requiredSkills:["엑셀"] },
  { postingId:"role-232",externalId:"177144",companyName:"현대로템",positionTitle:"항공우주 분야 신입 채용 · 시험장 설비 및 안전관리",jobFamily:"생산/품질",employmentType:"정규직",companyType:"대기업",deadline:"2026-09-20",sourceUrl:"https://hyundai-rotem.recruiter.co.kr/career/jobs/125768",coachReady:true,requiredSkills:["AutoCAD"] },
  { postingId:"role-230",externalId:"177145",companyName:"현대로템",positionTitle:"항공우주 분야 신입 채용 · 우주사업 기획",jobFamily:"연구개발",employmentType:"정규직",companyType:"대기업",deadline:"2026-09-20",sourceUrl:"https://hyundai-rotem.recruiter.co.kr/career/jobs/125768",coachReady:true,requiredSkills:["CATIA"] },
  { postingId:"role-252",externalId:"177150",companyName:"에이피알",positionTitle:"[26 신입채용] 글로벌 CX 운영·기획",jobFamily:"경영지원",employmentType:"정규직전환형",companyType:"중견기업",deadline:"2026-09-20",sourceUrl:"https://apr-careers.com/job_posting/SV1pC6BG",coachReady:true,requiredSkills:["Excel"] },
  { postingId:"role-253",externalId:"177151",companyName:"에이피알",positionTitle:"[26 신입채용] 메디큐브 국내 온라인 마케팅",jobFamily:"영업/마케팅",employmentType:"정규직전환형",companyType:"중견기업",deadline:"2026-09-20",sourceUrl:"https://apr-careers.com/job_posting/0vP9E3yo",coachReady:true,requiredSkills:["Photoshop","Premiere"] }
];

export const DEMO_CONTEXTS = DEMO_POSTINGS.map((posting) => ({
  ...posting,
  tier:"demo",
  responsibilities:[`${posting.positionTitle} 관련 업무 수행과 협업`, `${posting.requiredSkills.join(", ") || "직무 역량"}을 활용한 문제 해결`],
  preferredSkills:[],
  sourceUpdatedAt:"2026-09-17"
}));
