package tests

import (
	"sync"

	"golang.org/x/sync/errgroup"
)

// ruleid: goroutine-without-sync
func badFireAndForget() {
	go func() {
		doWork()
	}()
}

// ruleid: goroutine-without-sync
func badMultipleGoroutines() {
	for i := 0; i < 5; i++ {
		go func() {
			doWork()
		}()
	}
}

// ok: WaitGroup present
func okWithWaitGroup() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		doWork()
	}()
	wg.Wait()
}

// ok: errgroup present
func okWithErrgroup() error {
	g, _ := errgroup.WithContext(nil)
	g.Go(func() error {
		return doWorkErr()
	})
	return g.Wait()
}

func doWork()          {}
func doWorkErr() error { return nil }
