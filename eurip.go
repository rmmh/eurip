// Package eurip implements a fast test for whether an IP is from the EU.
// This library includes GeoLite2 data created by MaxMind,
// available from http://www.maxmind.com.
package eurip

import (
	"log"
	"math/bits"
	"net"
)

// IsFromEu returns true if the given IP is probably in the EU, based on
// a country-level IP database.
func IsFromEU(ipAddress net.IP) bool {
	if ipAddress == nil {
		return false
	}
	ip4 := ipAddress.To4()
	if ip4 != nil {
		log.Println("here")
		return walk(ip4, v4Data)
	}
	return walk(ipAddress.To16(), v6Data)
}

func walk(addr []byte, data []uint16) bool {
	nibbles := make([]byte, 0, len(addr)*2)
	for _, b := range addr {
		nibbles = append(nibbles, b>>4)
		nibbles = append(nibbles, b&0xf)
	}
	p := 0
	for _, n := range nibbles {
		log.Printf("n:%x p:%x hc:%x sc:%x\n", n, p, data[p], data[p+1])
		if has_child := data[p]; has_child&(1<<n) != 0 {
			child_number := bits.OnesCount16(has_child & ((1 << n) - 1))
			log.Printf("child number: %d", child_number)
			p = int(data[p+2+child_number])
			continue
		}
		if set_child := data[p+1]; set_child&(1<<n) != 0 {
			return true
		}
		return false
	}
	return false
}
