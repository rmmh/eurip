package eurip

import (
	"net"
	"testing"
)

func TestKnownRanges(t *testing.T) {
	for _, tc := range []struct {
		ip      string
		is_euro bool
	}{
		{"2.0.0.1", true},
		{"1.0.0.1", false},
		{"2.15.255.255", true},
		{"2.16.0.0", false},
		{"::0", false},
		{"2001:420:4000:1::", true},
	} {
		result := IsFromEU(net.ParseIP(tc.ip))
		if result != tc.is_euro {
			t.Errorf("IsFromEU(%s) != %v", tc.ip, tc.is_euro)
		}
	}
}
