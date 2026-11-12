# 🚀 래리 윌리엄스 변동성 돌파 백테스터

래리 윌리엄스(Larry Williams)의 **변동성 돌파(Volatility Breakout)** 전략을 국내 지수 ETF·개별주식 일봉 데이터로 검증하는 Streamlit 웹앱입니다. 블로그 **「AI시대의 투자 서바이벌」**(finsnap.tistory.com)의 전략 실험실 시리즈와 함께 쓰입니다.

- **라이브 앱**: https://finsnap-volatility.streamlit.app
- **터틀 트레이딩 버전**: https://finsnap-turtle.streamlit.app

## 전략 규칙

```
전일 레인지 = 전일 고가 − 전일 저가
목표가      = 당일 시가 + 전일 레인지 × K
매수        = 당일 고가 ≥ 목표가 이면 목표가에 진입 (시가가 이미 목표가를 넘긴 갭상승은 시가 체결)
청산        = 익일 시가 청산(기본형) 또는 당일 종가 청산(데이트레이딩)
```

- **K값**: 0.10 ~ 1.00 (0.05 단위). K가 낮을수록 진입이 잦고, 높을수록 강한 돌파만 잡습니다.
- **자금 관리**: 진입 신호마다 가용 현금 100% 투입, 정수 주 단위.
- **거래 비용**: 슬리피지 편도 0.05%, 수수료 편도 0.015%. KODEX 등 국내 주식형 ETF는 증권거래세 0%, 개별주식은 매도 시 0.18%를 반영합니다.

## 화면 구성

| 영역 | 내용 |
| --- | --- |
| 사이드바 | 종목(프리셋 4종 + 6자리 직접 입력), 자산 구분(ETF/개별주식), K값, 청산 방식, 초기 자본금, 슬리피지·수수료, 시작일 |
| 핵심 지표 | 최종 자산, 누적 수익률, CAGR, MDD, 승률, 총 거래 횟수, 건당 평균수익률(엣지), 샤프 지수 — 단순보유(B&H)와 나란히 비교 |
| 차트 | ① 누적 자산 vs 단순보유(로그 스케일) ② 언더워터 낙폭 비교 ③ 연도별 수익률 막대·표 |
| 매매일지 | 전체 체결 내역 테이블 + CSV 다운로드 |

## 데이터

- 네이버 금융 일봉 API(`api.finance.naver.com/siseJson.naver`)를 1차 소스로 사용하고, pykrx가 설치된 환경에서는 2차 경로로 시도합니다.
- 거래정지·휴장일의 0원 행, 고가<저가, 종가가 고저 범위를 벗어난 비정상 봉은 자동으로 제외합니다(액면분할 구간 왜곡 방지).
- 조회 결과는 `data/`에 CSV로 캐시되며, Streamlit에서는 1시간 TTL 캐시를 함께 사용합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

리눅스에서 한글 차트가 네모로 보이면 `packages.txt`의 `fonts-nanum`(데비안/우분투: `sudo apt install fonts-nanum`)을 설치하세요. macOS·Windows는 OS 기본 한글 폰트로 표시됩니다.

## 파일 구성

```
app.py            Streamlit 메인 애플리케이션
strategy.py       전일 레인지·목표가·진입 신호 계산
backtester.py     체결·청산·비용(슬리피지/수수료/거래세) 시뮬레이션 엔진
data_fetcher.py   일봉 수집(네이버 금융 → pykrx) 및 데이터 정제
metrics.py        CAGR·MDD·승률·손익비 등 성과 지표
requirements.txt  파이썬 패키지
packages.txt      Streamlit Cloud 시스템 패키지 (fonts-nanum)
```

## 주의

과거 데이터에 기반한 시뮬레이션이며 미래 수익을 보장하지 않습니다. 투자 판단과 그 결과에 대한 책임은 투자자 본인에게 있습니다.
