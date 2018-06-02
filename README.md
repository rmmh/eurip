# EurIP
Test if an IP is European with minimal overhead, based on MaxMind's Geolite2 data.

The data is currently (2018-06-02) ~113KB, plus <50 LOC to walk the structure. Lookup is O(1) since IP address length is fixed!

# Source
This is derived from [MaxMind's GeoLite2 Country Database](https://dev.maxmind.com/geoip/geoip2/geolite2/) for IPv4 and IPv6.

Country-level geolocation is generally reliable-- ISP IP allocation ranges rarely cross borders.

# Datastructure
To determine one bit of information about an IP, a bitset directed acyclic graph is used. 
Each node has up to 16 children, and there is a node for each nibble (4-bit segment) of an IP address. 
Some pointers are omitted by storing an additional 16+16 bits in each node indicating missing child pointers 
and which children indicate completely set bit ranges.

## Comparison
All numbers are from the 20180501 GeoLite2 database, 
which contains 53093 IPv4 and 11950 IPv6 CIDR ranges for the European Union.

| Method  | Size (KB) | zlib | lzma |
|-|-|-|-|
| Text (v4) |833.2|169.0|117.6|
| Text (v6)|191.7|34.4|16.9|
| Binary List (v4)|259.2|150.4|84.5|
| Binary List (v6)|198.4|36.1|16.3|
| Bitset DAG (v4)|88.8|66.9|62.0|
| Bitset DAG (v6)|23.5|12.8|11.3|
