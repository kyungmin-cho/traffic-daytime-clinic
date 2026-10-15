# 원자료가 data/raw에 이미 있으면 `make analyze figures verify`로 내려받기를 건너뛴다.
.NOTPARALLEL:
.PHONY: all data prepare analyze figures verify

RUN = uv run --frozen python

all: data analyze figures verify

data:
	$(RUN) src/data.py fetch

prepare:
	$(RUN) src/data.py prepare

analyze: prepare
	$(RUN) src/analysis.py

figures:
	$(RUN) src/figures.py

verify:
	$(RUN) src/verify.py
