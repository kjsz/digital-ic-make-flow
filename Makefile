# Run here or with make -C /path/to/project. Dependencies stay in Make.
.DEFAULT_GOAL := help
.NOTPARALLEL:
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
-include config.mk
-include tech/current/tech.mk
include flow/settings.mk
.PHONY: help check summary clean clean-preview sim verdi cov dc formal postsim postverdi postverdi_sdf postsim_sdf init floorplan powerplan placement cts route chipfinish pnr open merge drc lvs rc pt test
help:
	@$(PYTHON) flow/flow.py help
check:
	@$(PYTHON) flow/flow.py check
summary:
	@$(PYTHON) flow/flow.py summary
clean clean-preview:
	@$(PYTHON) flow/flow.py $@
sim:
	@$(PYTHON) flow/flow.py run sim
verdi: sim
	@$(PYTHON) flow/flow.py open verdi
cov:
	@$(PYTHON) flow/flow.py run cov
ifeq ($(GUI),1)
	@$(PYTHON) flow/flow.py open cov
endif
dc:
	@$(PYTHON) flow/flow.py run dc
formal: dc
	@$(PYTHON) flow/flow.py run formal
postsim: $(if $(filter chipfinish,$(GATE_STAGE)),chipfinish,dc)
	@$(PYTHON) flow/flow.py run postsim
postverdi: postsim
	@$(PYTHON) flow/flow.py open postverdi
postsim_sdf: chipfinish
	@$(PYTHON) flow/flow.py run postsim_sdf
init: dc
floorplan: init
powerplan: floorplan
placement: powerplan
cts: placement
route: cts
chipfinish: route
init floorplan powerplan placement cts route chipfinish:
	@$(PYTHON) flow/flow.py run $@
pnr: chipfinish
open:
	@$(PYTHON) flow/flow.py open pnr
merge: chipfinish
	@$(PYTHON) flow/flow.py run merge
drc: merge
	@$(PYTHON) flow/flow.py open drc
lvs: merge hcell
	@$(PYTHON) flow/flow.py run lvs-input
	@$(PYTHON) flow/flow.py open lvs
rc: chipfinish
	@$(PYTHON) flow/flow.py run rc
pt: rc
	@$(PYTHON) flow/flow.py run pt
test:
	@$(PYTHON) -m unittest discover -s tests -v

.PHONY: eco eco-accept eco-use-original
eco: chipfinish
	@$(PYTHON) flow/flow.py open eco
eco-accept:
	@$(PYTHON) flow/flow.py eco-accept
eco-use-original:
	@$(PYTHON) flow/flow.py eco-use-original

.PHONY: hcell
hcell: chipfinish
	@$(PYTHON) flow/flow.py run hcell

.PHONY: route-resume
route-resume:
	@$(PYTHON) flow/flow.py route-resume

.PHONY: eco-history eco-rollback reports
eco-history eco-rollback reports:
	@$(PYTHON) flow/flow.py $@
# SDF 回标门级仿真完成后打开对应波形。
postverdi_sdf: postsim_sdf
	@$(PYTHON) flow/flow.py open postverdi_sdf

# 无依赖：只收集当前最终版本已存在的交付文件，缺项跳过。
.PHONY: output
output:
	@$(PYTHON) flow/flow.py output
