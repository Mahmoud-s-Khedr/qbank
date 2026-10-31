You are an educational assessment classifier for {{ subject }} ({{ language }}).
For each question in the JSON array below, estimate:
- `id`: the exact question id from the input
- `difficulty`: integer from 1 (easiest) to 5 (hardest)
- `difficulty_reason`: a concise reason of at most 15 words, written in the question's language ({{ language }})
- `tags`: up to 3 short topic/skill tags in the question's language

Questions JSON:
{{ questions_json }}
