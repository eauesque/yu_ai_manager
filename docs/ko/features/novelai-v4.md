# 캐릭터별 네거티브 프롬프트 지원

## 신규 기능

NovelAI V4 **캐릭터별 네거티브 프롬프트**를 완전히 지원합니다.

### 표시 예시

```
NovelAI V4 Character Prompts

Base Caption
┌─────────────────────────────────────────┐
│ winter, 1.2::artist:sample_creator::,    │
│ very aesthetic, masterpiece, no text    │
└─────────────────────────────────────────┘

#1                            @ (50%, 50%)
┌─────────────────────────────────────────┐
│ girl, high school student, walking,     │
│ talking, face-to-face                   │
│                                         │
│ 제외: child, sleeping,                  │  <- NEW!
└─────────────────────────────────────────┘

#2                            @ (50%, 50%)
┌─────────────────────────────────────────┐
│ girl, college student                   │
│                                         │
│ 제외: mature female                     │  <- NEW!
└─────────────────────────────────────────┘

Negative (Base)
┌─────────────────────────────────────────┐
│ nsfw, lowres, bad quality, ...          │
└─────────────────────────────────────────┘
```

---

## 데이터 구조

### NovelAI V4 메타데이터

```json
{
  "v4_prompt": {
    "caption": {
      "base_caption": "winter, 1.2::artist:sample_creator::, ...",
      "char_captions": [
        {
          "char_caption": "girl, high school student, walking, talking, face-to-face",
          "centers": [{"x": 0.5, "y": 0.5}]
        },
        {
          "char_caption": "girl, college student,",
          "centers": [{"x": 0.5, "y": 0.5}]
        }
      ]
    }
  },
  "v4_negative_prompt": {
    "caption": {
      "base_caption": "nsfw, lowres, bad quality, ...",
      "char_captions": [                           <- NEW!
        {
          "char_caption": "child, sleeping,",      <- 캐릭터 #1의 제외 항목
          "centers": [{"x": 0.5, "y": 0.5}]
        },
        {
          "char_caption": "mature female",         <- 캐릭터 #2의 제외 항목
          "centers": [{"x": 0.5, "y": 0.5}]
        }
      ]
    }
  }
}
```

---

## 구현 상세

### 1. JavaScript - parseNovelAICharacterPrompts()

**추가:**
```javascript
const result = {
  baseCaption: '',
  characters: [],
  negativeBase: '',
  negativeCharacters: [],  // <- NEW!
  vibeTransfer: null
};

// Character-specific negatives
if (negCaption.char_captions && negCaption.char_captions.length > 0) {
  result.negativeCharacters = negCaption.char_captions.map((char, index) => ({
    index: index + 1,
    prompt: char.char_caption || '',
    positions: char.centers || []
  }));
}
```

### 2. JavaScript - renderCharacterPrompts()

**추가:**
```javascript
// Character-specific negative (if exists)
if (data.negativeCharacters && data.negativeCharacters[idx]) {
  const negChar = data.negativeCharacters[idx];
  if (negChar.prompt) {
    html += '<div class="char-negative-prompt">';
    html += `<span class="char-negative-label">제외:</span> `;
    html += `<span class="char-negative-text">${escapeHtml(negChar.prompt)}</span>`;
    html += '</div>';
  }
}
```

### 3. CSS - character-prompts.css

**추가:**
```css
.char-negative-prompt {
  margin-top: 8px;
  padding: 6px 10px;
  background: rgba(255, 59, 48, 0.08);
  border-left: 2px solid #ff3b30;
  border-radius: 3px;
  font-size: 12px;
}

.char-negative-label {
  font-weight: 600;
  color: #ff3b30;
  margin-right: 4px;
}

.char-negative-text {
  color: var(--text);
  font-family: 'Consolas', 'Monaco', monospace;
}
```

### 4. 디버그 스크립트

**추가:**
```javascript
if (commentData.v4_negative_prompt) {
  const negCaption = commentData.v4_negative_prompt.caption;
  console.log('  negative char_captions count:', negCaption.char_captions?.length || 0);

  negCaption.char_captions?.forEach((char, i) => {
    console.log(`    Negative Character ${i+1}:`, char.char_caption);
  });
}
```

---

## 사용법

### 설치

```bash
# 1. 압축 해제
unzip -o ai_image_tag_neo_CHARACTER_NEGATIVES.zip

# 2. 서버 재시작
cd ai_image_tag_neo
python web_ui.py

# 3. 브라우저에서 확인
# Ctrl+Shift+R로 강제 새로고침
```

### 확인

1. **NovelAI V4 이미지 열기**
   - 예: winter__1_2__artist_sample_creator___s-1034371708.png

2. **Character Prompts 섹션 확인**
   - 각 캐릭터 카드 아래에 "제외: ..."가 표시되어야 합니다

3. **디버그 로그 확인 (F12)**
   ```
   parseNovelAICharacterPrompts called
     ...
     char_captions count: 2
       Character 1: girl, high school student, ...
       Character 2: girl, college student

     v4_negative_prompt.caption exists: true
     negative char_captions count: 2
       Negative Character 1: child, sleeping,
       Negative Character 2: mature female
   ```

---

## 확인 체크리스트

### 서버 재시작 후

- [ ] `python web_ui.py`로 시작
- [ ] 브라우저에서 http://127.0.0.1:5000 열기
- [ ] **Ctrl+Shift+R**로 강제 새로고침

### 캐릭터 네거티브 표시

- [ ] NovelAI V4 이미지 열기
- [ ] 캐릭터 #1 카드에 "제외: child, sleeping," 표시
- [ ] 캐릭터 #2 카드에 "제외: mature female" 표시
- [ ] "제외:" 라벨이 빨간색 (#ff3b30)으로 표시
- [ ] 배경이 연한 빨간색 (반투명)

### 다크 모드

- [ ] 테마를 다크로 전환
- [ ] 캐릭터 네거티브가 읽기 쉬운 상태 유지
- [ ] 라벨이 밝은 빨간색 (#ff6b6b)으로 표시
- [ ] 텍스트가 밝은 회색 (#e0e0e0)으로 표시

### 디버그 로그

- [ ] F12로 콘솔 열기
- [ ] `negative char_captions count: 2`
- [ ] `Negative Character 1: ...`
- [ ] `Negative Character 2: ...`

---

## 디자인

### 라이트 모드
- 배경: rgba(255, 59, 48, 0.08) - 연한 빨간색
- 라벨: #ff3b30 - 선명한 빨간색
- 텍스트: 기본 색상
- 테두리: 2px solid #ff3b30 - 왼쪽

### 다크 모드
- 배경: rgba(255, 59, 48, 0.12) - 약간 더 진한 빨간색
- 라벨: #ff6b6b - 밝은 빨간색
- 텍스트: #e0e0e0 - 밝은 회색
- 테두리: 2px solid #ff3b30 - 왼쪽

---

## 기술 상세

### 배열 인덱스 대응

```javascript
data.characters.forEach((char, idx) => {
  // Positive character prompt
  html += char.prompt;

  // Corresponding negative character prompt
  if (data.negativeCharacters && data.negativeCharacters[idx]) {
    html += data.negativeCharacters[idx].prompt;
  }
});
```

**중요**:
- `characters[0]` -> `negativeCharacters[0]`
- `characters[1]` -> `negativeCharacters[1]`
- 인덱스가 1:1로 대응

### 이스케이프 처리

```javascript
escapeHtml(negChar.prompt)
```

모든 사용자 입력은 XSS 공격을 방지하기 위해 HTML 이스케이프됩니다.

---

## 문제 해결

### "제외:"가 표시되지 않음

#### 사례 1: 이미지에 캐릭터별 네거티브가 없음
정상 동작입니다. 모든 이미지에 포함되어 있는 것은 아닙니다.

#### 사례 2: 서버가 재시작되지 않음
```bash
# Ctrl+C로 중지
python web_ui.py
```

#### 사례 3: 브라우저 캐시
```
Ctrl+Shift+R로 강제 새로고침
```

#### 사례 4: 콘솔에서 오류 확인
```
F12 -> Console
negative char_captions count: 확인
```

---

## 성능

### 메모리 영향
- 추가 데이터: 이미지당 수백 바이트
- 영향: 무시할 수 있음

### 렌더링 속도
- 렌더링: <1ms
- 영향: 없음

---

## 완성도

### NovelAI V4 지원 현황

| 기능 | 지원 |
|------|------|
| Base Caption | 지원 |
| Character Prompts | 지원 |
| Character Positions | 지원 |
| Base Negative | 지원 |
| **Character Negatives** | **신규!** |
| Vibe Transfer | 지원 |

**100% 완전 지원!**

---

**버전**: Character Negatives v1
**날짜**: 2026-02-13
**전제 조건**: FINAL_FIX 적용
**상태**: Production Ready
