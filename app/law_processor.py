import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import re
import os
import unicodedata
from collections import defaultdict

OC = os.getenv("OC", "chetera")
BASE = "http://www.law.go.kr"

def highlight(text, query):
    """검색어를 HTML로 하이라이트 처리해주는 함수"""
    if not query or not text:
        return text
    # 정규식 특수문자 이스케이프
    escaped_query = re.escape(query)
    # 대소문자 구분없이 검색
    pattern = re.compile(f'({escaped_query})', re.IGNORECASE)
    return pattern.sub(r'<mark>\1</mark>', text)

def get_law_list_from_api(query):
    exact_query = f'"{query}"'
    encoded_query = quote(exact_query)
    page = 1
    laws = []
    while True:
        url = f"{BASE}/DRF/lawSearch.do?OC={OC}&target=law&type=XML&display=100&page={page}&search=2&knd=A0002&query={encoded_query}"
        try:
            res = requests.get(url, timeout=10)
            res.encoding = 'utf-8'
            if res.status_code != 200:
                break
            root = ET.fromstring(res.content)
            for law in root.findall("law"):
                laws.append({
                    "법령명": law.findtext("법령명한글", "").strip(),
                    "MST": law.findtext("법령일련번호", "")
                })
            if len(root.findall("law")) < 100:
                break
            page += 1
        except Exception as e:
            print(f"법률 검색 중 오류 발생: {e}")
            break
    # 디버깅을 위해 검색된 법률 목록 출력
    print(f"검색된 법률 수: {len(laws)}")
    for idx, law in enumerate(laws):
        print(f"{idx+1}. {law['법령명']}")
    return laws

def get_law_text_by_mst(mst):
    url = f"{BASE}/DRF/lawService.do?OC={OC}&target=law&MST={mst}&type=XML"
    try:
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code == 200:
            # XML 내용 출력 (디버깅)
            # print(f"XML 데이터 크기: {len(res.content)} 바이트")
            return res.content
        else:
            print(f"법령 XML 가져오기 실패: 상태 코드 {res.status_code}")
            return None
    except Exception as e:
        print(f"법령 XML 가져오기 중 오류 발생: {e}")
        return None

def clean(text):
    return re.sub(r"\s+", "", text or "")

def normalize_number(text):
    try:
        return str(int(unicodedata.numeric(text)))
    except:
        return text

def make_article_number(조문번호, 조문가지번호):
    return f"제{조문번호}조의{조문가지번호}" if 조문가지번호 and 조문가지번호 != "0" else f"제{조문번호}조"

def has_batchim(word):
    """단어의 마지막 글자에 받침이 있는지 확인"""
    if not word:
        return False
    code = ord(word[-1]) - 0xAC00
    return (code % 28) != 0

def has_rieul_batchim(word):
    """단어의 마지막 글자의 받침이 ㄹ인지 확인"""
    if not word:
        return False
    code = ord(word[-1]) - 0xAC00
    return (code % 28) == 8  # ㄹ받침 코드는 8

def extract_chunk_and_josa(token, searchword):
    """검색어를 포함하는 덩어리와 조사를 추출"""
    # 제외할 접미사 리스트 (덩어리에 포함시키지 않을 것들)
    suffix_exclude = ["의", "에", "에서", "으로서", "등", "등인", "에게", "만", "만을", "만이", "만은", "만에", "만으로"]
    
    # 처리할 조사 리스트
    josa_list = ["을", "를", "과", "와", "이", "가", "이나", "나", "으로", "로", "은", "는", "란", "이란", "라", "이라"]
    
    # 원본 토큰 저장
    original_token = token
    suffix = None
    
    # 검색어 자체가 토큰인 경우 바로 반환
    if token == searchword:
        return token, None, None
    
    # 토큰에 검색어가 포함되어 있지 않으면 바로 반환
    if searchword not in token:
        return token, None, None
    
    # 1. 접미사 제거 시도 (단, 이 접미사들은 덩어리에 포함시키지 않음)
    for s in sorted(suffix_exclude, key=len, reverse=True):
        if token.endswith(s) and len(token) > len(s):
            # 검색어와 접미사가 분리되어 있는지 확인
            if searchword + s == token:
                # 이 경우 검색어 자체를 반환하고 접미사는 별도로 처리
                return searchword, None, s
            elif token.endswith(searchword + s):
                # 뒤쪽에 접미사가 붙은 경우 (예: "검색어의")
                prefix = token[:-len(searchword + s)]
                # 접두어가 있는 경우 전체 토큰 반환
                if prefix:
                    return token, None, None
                # 접두어가 없는 경우 검색어만 반환
                else:
                    return searchword, None, s
            suffix = s
            token = token[:-len(s)]
            break
    
    # 2. 조사 확인
    josa = None
    chunk = token
    
    # 토큰이 "검색어 + 조사"로 정확히 구성된 경우
    for j in sorted(josa_list, key=len, reverse=True):
        if token == searchword + j:
            return searchword, j, suffix
    
    # 3. 토큰 내의 위치 찾기
    start_pos = token.find(searchword)
    if start_pos != -1:
        end_pos = start_pos + len(searchword)
        
        # 검색어가 토큰의 끝에 있는 경우
        if end_pos == len(token):
            if start_pos == 0:  # 토큰이 정확히 검색어인 경우
                return searchword, None, suffix
            else:  # 검색어 앞에 다른 내용이 있는 경우
                return token, None, suffix
                
        # 검색어 뒤에 조사가 있는지 확인
        for j in sorted(josa_list, key=len, reverse=True):
            if token[end_pos:].startswith(j):
                # 검색어 + 조사 앞에 다른 내용이 있는 경우
                if start_pos > 0:
                    return token, None, suffix
                # 검색어 + 조사 뒤에 다른 내용이 있는 경우
                elif end_pos + len(j) < len(token):
                    return token, None, suffix
                # 정확히 "검색어 + 조사"인 경우
                else:
                    return searchword, j, suffix
    
    # 4. 토큰이 검색어를 포함하지만 조건에 맞지 않는 경우 토큰 전체 반환
    return token, None, suffix
    
def apply_josa_rule(orig, replaced, josa):
    """개정문 조사 규칙에 따라 적절한 형식 반환"""
    # 동일한 단어면 변경할 필요 없음
    if orig == replaced:
        return f'"{orig}"를 "{replaced}"로 한다.'
        
    orig_has_batchim = has_batchim(orig)
    replaced_has_batchim = has_batchim(replaced)
    replaced_has_rieul = has_rieul_batchim(replaced)
    
    # 조사가 없는 경우 (규칙 0)
    if josa is None:
        if not orig_has_batchim:  # 규칙 0-1: A가 받침 없는 경우
            if not replaced_has_batchim or replaced_has_rieul:  # 규칙 0-1-1, 0-1-2-1
                return f'"{orig}"를 "{replaced}"로 한다.'
            else:  # 규칙 0-1-2-2: B의 받침이 ㄹ이 아닌 경우
                return f'"{orig}"를 "{replaced}"으로 한다.'
        else:  # 규칙 0-2: A가 받침 있는 경우
            if not replaced_has_batchim or replaced_has_rieul:  # 규칙 0-2-1, 0-2-2-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 0-2-2-2: B의 받침이 ㄹ이 아닌 경우
                return f'"{orig}"을 "{replaced}"으로 한다.'
    
    # 조사별 규칙 처리
    if josa == "을":  # 규칙 1
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 1-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 1-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 1-2
            return f'"{orig}을"을 "{replaced}를"로 한다.'
    
    elif josa == "를":  # 규칙 2
        if replaced_has_batchim:  # 규칙 2-1
            return f'"{orig}를"을 "{replaced}을"로 한다.'
        else:  # 규칙 2-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "과":  # 규칙 3
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 3-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 3-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 3-2
            return f'"{orig}과"를 "{replaced}와"로 한다.'
    
    elif josa == "와":  # 규칙 4
        if replaced_has_batchim:  # 규칙 4-1
            return f'"{orig}와"를 "{replaced}과"로 한다.'
        else:  # 규칙 4-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "이":  # 규칙 5
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 5-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 5-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 5-2
            return f'"{orig}이"를 "{replaced}가"로 한다.'
    
    elif josa == "가":  # 규칙 6
        if replaced_has_batchim:  # 규칙 6-1
            return f'"{orig}가"를 "{replaced}이"로 한다.'
        else:  # 규칙 6-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "이나":  # 규칙 7
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 7-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 7-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 7-2
            return f'"{orig}이나"를 "{replaced}나"로 한다.'
    
    elif josa == "나":  # 규칙 8
        if replaced_has_batchim:  # 규칙 8-1
            return f'"{orig}나"를 "{replaced}이나"로 한다.'
        else:  # 규칙 8-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "으로":  # 규칙 9
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 9-1-1
                return f'"{orig}으로"를 "{replaced}로"로 한다.'
            else:  # 규칙 9-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 9-2
            return f'"{orig}으로"를 "{replaced}로"로 한다.'
    
    elif josa == "로":  # 규칙 10
        if orig_has_batchim:  # 규칙 10-1: A에 받침이 있는 경우
            if replaced_has_batchim:
                if replaced_has_rieul:  # 규칙 10-1-1-1
                    return f'"{orig}"을 "{replaced}"로 한다.'
                else:  # 규칙 10-1-1-2
                    return f'"{orig}로"를 "{replaced}으로"로 한다.'
            else:  # 규칙 10-1-2
                return f'"{orig}"을 "{replaced}"로 한다.'
        else:  # 규칙 10-2: A에 받침이 없는 경우
            if replaced_has_batchim:
                if replaced_has_rieul:  # 규칙 10-2-1-1
                    return f'"{orig}"를 "{replaced}"로 한다.'
                else:  # 규칙 10-2-1-2
                    return f'"{orig}로"를 "{replaced}으로"로 한다.'
            else:  # 규칙 10-2-2
                return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "는":  # 규칙 11
        if replaced_has_batchim:  # 규칙 11-1
            return f'"{orig}는"을 "{replaced}은"으로 한다.'
        else:  # 규칙 11-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "은":  # 규칙 12
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 12-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 12-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 12-2
            return f'"{orig}은"을 "{replaced}는"으로 한다.'
    
    elif josa == "란":  # 규칙 13
        if replaced_has_batchim:  # 규칙 13-1
            return f'"{orig}란"을 "{replaced}이란"으로 한다.'
        else:  # 규칙 13-2
            return f'"{orig}"를 "{replaced}"로 한다.'
    
    elif josa == "이란":  # 규칙 14
        if replaced_has_batchim:
            if replaced_has_rieul:  # 규칙 14-1-1
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:  # 규칙 14-1-2
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:  # 규칙 14-2
            return f'"{orig}이란"을 "{replaced}란"으로 한다.'
            
    elif josa == "라":  # 추가 규칙: "라" 조사
        if replaced_has_batchim:  # 받침이 있으면 "이라"
            return f'"{orig}라"를 "{replaced}이라"로 한다.'
        else:  # 받침이 없으면 그대로 "라"
            return f'"{orig}라"를 "{replaced}라"로 한다.'
            
    elif josa == "이라":  # 추가 규칙: "이라" 조사
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}이라"를 "{replaced}이라"로 한다.'
            else:
                return f'"{orig}이라"를 "{replaced}이라"로 한다.'
        else:
            return f'"{orig}이라"를 "{replaced}라"로 한다.'
    
    # 기본 출력 형식
    if orig_has_batchim:
        return f'"{orig}"을 "{replaced}"로 한다.'
    else:
        return f'"{orig}"를 "{replaced}"로 한다.'

def format_location(location):
    """위치 정보 형식 수정: 항번호가 비어있는 경우와 호번호, 목번호의 period 제거"""
    # 항번호가 비어있는 경우 "제항" 제거
    location = re.sub(r'제(?=항)', '', location)
    
    # 호번호와 목번호 뒤의 period(.) 제거
    location = re.sub(r'(\d+)\.호', r'\1호', location)
    location = re.sub(r'([가-힣])\.목', r'\1목', location)
    
    return location

def group_locations(loc_list):
    """위치 정보 그룹화"""
    # 각 위치 문자열에 형식 수정 적용
    formatted_locs = [format_location(loc) for loc in loc_list]
    
    if len(formatted_locs) == 1:
        return formatted_locs[0]
    return 'ㆍ'.join(formatted_locs[:-1]) + ' 및 ' + formatted_locs[-1]

def consolidate_locations_by_rule(law_name, rule_map):
    """같은 법률 내에서 같은 개정 규칙을 가진 위치를 통합"""
    result_lines = []
    
    # "의"가 포함된 위치와 단순 검색어만 있는 위치를 분리
    simple_rules = {}
    special_rules = {}
    
    for rule, locations in rule_map.items():
        # "~란" 조사를 포함하는 규칙인 경우 별도 처리
        if '"란' in rule or '"이란' in rule:
            special_rules[rule] = locations
        # "의"가 포함된 규칙인 경우 별도 처리
        elif '"의"' in rule:
            special_rules[rule] = locations
        # 일반 규칙
        else:
            if rule not in simple_rules:
                simple_rules[rule] = []
            simple_rules[rule].extend(locations)
    
    # 1. 단순 규칙 먼저 처리 (동일한 규칙의 위치 통합)
    if simple_rules:
        for rule, locations in simple_rules.items():
            loc_str = group_locations(sorted(set(locations)))
            result_lines.append(f"{loc_str} 중 {rule}")
    
    # 2. 특수 규칙 처리
    if special_rules:
        for rule, locations in special_rules.items():
            loc_str = group_locations(sorted(set(locations)))
            result_lines.append(f"{loc_str} 중 {rule}")
    
    # 결과 반환
    return result_lines

def run_search_logic(query, unit="법률"):
    """검색 로직 실행 함수"""
    result_dict = {}
    keyword_clean = clean(query)
    for law in get_law_list_from_api(query):
        mst = law["MST"]
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            continue
        tree = ET.fromstring(xml_data)
        articles = tree.findall(".//조문단위")
        law_results = []
        for article in articles:
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조문가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            조문내용 = article.findtext("조문내용", "") or ""
            항들 = article.findall("항")
            출력덩어리 = []
            조출력 = keyword_clean in clean(조문내용)
            첫_항출력됨 = False
            if 조출력:
                출력덩어리.append(highlight(조문내용, query))
            for 항 in 항들:
                항번호 = normalize_number(항.findtext("항번호", "").strip())
                항내용 = 항.findtext("항내용", "") or ""
                항출력 = keyword_clean in clean(항내용)
                항덩어리 = []
                하위검색됨 = False
                for 호 in 항.findall("호"):
                    호내용 = 호.findtext("호내용", "") or ""
                    호출력 = keyword_clean in clean(호내용)
                    if 호출력:
                        하위검색됨 = True
                        항덩어리.append("&nbsp;&nbsp;" + highlight(호내용, query))
                    for 목 in 호.findall("목"):
                        for m in 목.findall("목내용"):
                            if m.text and keyword_clean in clean(m.text):
                                줄들 = [line.strip() for line in m.text.splitlines() if line.strip()]
                                줄들 = [highlight(line, query) for line in 줄들]
                                if 줄들:
                                    하위검색됨 = True
                                    항덩어리.append(
                                        "<div style='margin:0;padding:0'>" +
                                        "<br>".join("&nbsp;&nbsp;&nbsp;&nbsp;" + line for line in 줄들) +
                                        "</div>"
                                    )
                if 항출력 or 하위검색됨:
                    if not 조출력 and not 첫_항출력됨:
                        출력덩어리.append(f"{highlight(조문내용, query)} {highlight(항내용, query)}")
                        첫_항출력됨 = True
                    elif not 첫_항출력됨:
                        출력덩어리.append(highlight(항내용, query))
                        첫_항출력됨 = True
                    else:
                        출력덩어리.append(highlight(항내용, query))
                    출력덩어리.extend(항덩어리)
            if 출력덩어리:
                law_results.append("<br>".join(출력덩어리))
        if law_results:
            result_dict[law["법령명"]] = law_results
    return result_dict

def run_amendment_logic(find_word, replace_word):
    """개정문 생성 로직"""
    amendment_results = []
    skipped_laws = []  # 디버깅을 위해 누락된 법률 추적
    
    laws = get_law_list_from_api(find_word)
    print(f"총 {len(laws)}개 법률이 검색되었습니다.")
    
    for idx, law in enumerate(laws):
        law_name = law["법령명"]
        mst = law["MST"]
        print(f"처리 중: {idx+1}/{len(laws)} - {law_name} (MST: {mst})")  # 디버깅 추가
        
        xml_data = get_law_text_by_mst(mst)
        if not xml_data:
            skipped_laws.append(f"{law_name}: XML 데이터 없음")
            continue
            
        try:
            tree = ET.fromstring(xml_data)
        except ET.ParseError as e:
            skipped_laws.append(f"{law_name}: XML 파싱 오류 - {str(e)}")
            continue
            
        articles = tree.findall(".//조문단위")
        if not articles:
            skipped_laws.append(f"{law_name}: 조문단위 없음")
            continue
            
        print(f"조문 개수: {len(articles)}")  # 디버깅 추가
        
        chunk_map = defaultdict(list)
        
        # 법률에서 검색어의 모든 출현을 찾기 위한 디버깅 변수
        found_matches = 0
        
        # 법률의 모든 텍스트 내용을 검색
        for article in articles:
            # 조문
            조번호 = article.findtext("조문번호", "").strip()
            조가지번호 = article.findtext("조문가지번호", "").strip()
            조문식별자 = make_article_number(조번호, 조가지번호)
            
            # 조문내용에서 검색
            조문내용 = article.findtext("조문내용", "") or ""
            if find_word in 조문내용:
                found_matches += 1
                print(f"매치 발견: {조문식별자} 조문내용")  # 디버깅 추가
                tokens = re.findall(r'[가-힣A-Za-z0-9]+', 조문내용)
                for token in tokens:
                    if find_word in token:
                        chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                        replaced = chunk.replace(find_word, replace_word)
                        location = f"{조문식별자}"
                        chunk_map[(chunk, replaced, josa, suffix)].append(location)

            # 항 내용 검색
            for 항 in article.findall("항"):
                항번호 = normalize_number(항.findtext("항번호", "").strip())
                항번호_부분 = f"제{항번호}항" if 항번호 else ""
                
                항내용 = 항.findtext("항내용", "") or ""
                if find_word in 항내용:
                    found_matches += 1
                    print(f"매치 발견: {조문식별자}{항번호_부분} 항내용")  # 디버깅 추가
                    tokens = re.findall(r'[가-힣A-Za-z0-9]+', 항내용)
                    for token in tokens:
                        if find_word in token:
                            chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                            replaced = chunk.replace(find_word, replace_word)
                            location = f"{조문식별자}{항번호_부분}"
                            chunk_map[(chunk, replaced, josa, suffix)].append(location)
                
                # 호 내용 검색
                for 호 in 항.findall("호"):
                    호번호 = 호.findtext("호번호")
                    호내용 = 호.findtext("호내용", "") or ""
                    if find_word in 호내용:
                        found_matches += 1
                        print(f"매치 발견: {조문식별자}{항번호_부분}제{호번호}호 호내용")  # 디버깅 추가
                        tokens = re.findall(r'[가-힣A-Za-z0-9]+', 호내용)
                        for token in tokens:
                            if find_word in token:
                                chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                                replaced = chunk.replace(find_word, replace_word)
                                location = f"{조문식별자}{항번호_부분}제{호번호}호"
                                chunk_map[(chunk, replaced, josa, suffix)].append(location)

                    # 목 내용 검색
                    for 목 in 호.findall("목"):
                        목번호 = 목.findtext("목번호")
                        for m in 목.findall("목내용"):
                            if not m.text:
                                continue
                                
                            if find_word in m.text:
                                found_matches += 1
                                print(f"매치 발견: {조문식별자}{항번호_부분}제{호번호}호{목번호}목 목내용")  # 디버깅 추가
                                줄들 = [line.strip() for line in m.text.splitlines() if line.strip()]
                                for 줄 in 줄들:
                                    if find_word in 줄:
                                        tokens = re.findall(r'[가-힣A-Za-z0-9]+', 줄)
                                        for token in tokens:
                                            if find_word in token:
                                                chunk, josa, suffix = extract_chunk_and_josa(token, find_word)
                                                replaced = chunk.replace(find_word, replace_word)
                                                location = f"{조문식별자}{항번호_부분}제{호번호}호{목번호}목"
                                                chunk_map[(chunk, replaced, josa, suffix)].append(location)

        # 매칭된 내용이 있지만 chunk_map에 추가되지 않은 경우
        if found_matches > 0 and not chunk_map:
            print(f"경고: {law_name}에서 {found_matches}개 매치 발견되었으나 chunk_map에 추가되지 않음")
            
            # 디버깅: 검색어를 포함하는 부분을 출력하여 문제 원인 파악
            for article in articles:
                조문내용 = article.findtext("조문내용", "") or ""
                if find_word in 조문내용:
                    print(f"누락된 검색어 위치 (조문내용): {조문내용}")
                    print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 조문내용)}")
                
                for 항 in article.findall("항"):
                    항내용 = 항.findtext("항내용", "") or ""
                    if find_word in 항내용:
                        print(f"누락된 검색어 위치 (항내용): {항내용}")
                        print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 항내용)}")
                    
                    for 호 in 항.findall("호"):
                        호내용 = 호.findtext("호내용", "") or ""
                        if find_word in 호내용:
                            print(f"누락된 검색어 위치 (호내용): {호내용}")
                            print(f"토큰: {re.findall(r'[가-힣A-Za-z0-9]+', 호내용)}")
            
            skipped_laws.append(f"{law_name}: 검색어 {found_matches}개 발견되었으나 chunk_map에 추가되지 않음")
            
        if not chunk_map:
            continue
        
        # 디버깅: chunk_map 내용 출력
        print(f"chunk_map 항목 수: {len(chunk_map)}")
        for (chunk, replaced, josa, suffix), locations in chunk_map.items():
            print(f"chunk: '{chunk}', replaced: '{replaced}', josa: '{josa}', suffix: '{suffix}', locations: {locations}")
        
        # 같은 출력 형식을 가진 항목들을 그룹화
        rule_map = defaultdict(list)
        for (chunk, replaced, josa, suffix), locations in chunk_map.items():
            # 접미사 처리
            if suffix and suffix != "의":  # "의"는 개별 처리하지 않음
                orig_with_suffix = chunk + suffix
                replaced_with_suffix = replaced + suffix
                rule = apply_josa_rule(orig_with_suffix, replaced_with_suffix, josa)
            else:
                rule = apply_josa_rule(chunk, replaced, josa)
                
            rule_map[rule].extend(sorted(set(locations)))
        
        # 디버깅: rule_map 내용 출력
        print(f"rule_map 항목 수: {len(rule_map)}")
        for rule, locations in rule_map.items():
            print(f"rule: '{rule}', locations: {locations}")
        
        # 그룹화된 항목들을 정렬하여 출력
        result_lines = []
        for rule, locations in rule_map.items():
            loc_str = group_locations(sorted(set(locations)))
            result_lines.append(f"{loc_str} 중 {rule}")
            
# run_amendment_logic 함수 내의 결과 생성 부분 (전체 함수 중 일부만 수정)
# 변경된 법률에 대한 개정문 생성 (줄바꿈 개선)
if result_lines:
    prefix = chr(9312 + idx) if idx < 20 else f'({idx + 1})'
    amendment = f"{prefix} {law_name} 일부를 다음과 같이 개정한다.\n"
    # 각 개정 규칙마다 줄바꿈 추가
    amendment += "\n".join(result_lines)
    amendment_results.append(amendment)
else:
    skipped_laws.append(f"{law_name}: 결과줄이 생성되지 않음")

# 디버깅 정보 출력
if skipped_laws:
   print("누락된 법률 목록:", skipped_laws)
        
# 함수의 리턴문 (함수 마지막에 위치, 들여쓰기 없음)
return amendment_results if amendment_results else ["⚠️ 개정 대상 조문이 없습니다."]
