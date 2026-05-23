TUXPKG_MIN_COVERAGE = 74

export PROJECT := roxcal

all: typecheck style flake8

include $(shell tuxpkg get-makefile)

stylecheck: style flake8
