.PHONY: data

all: euro_v6.btr data.go

data: GeoLite2-Country-CSV.zip

GeoLite2-Country-CSV.zip:
	curl -O http://geolite.maxmind.com/download/geoip/database/GeoLite2-Country-CSV.zip

euro_v6.btr: GeoLite2-Country-CSV.zip
	./process.py

data.go: codegen.py euro_v6.btr
	./codegen.py --go
