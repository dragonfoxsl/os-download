package main

import (
	"bufio"
	"fmt"
	"log"
	"math"
	"os"
	"time"

	"github.com/cavaliergopher/grab/v3"
)

func main() {

	// Open OS download links file
	f, err := os.Open("./os-links/os.txt")
	if err != nil {
		log.Fatal(err)
	}
	// remember to close the file at the end of the program
	defer f.Close()

	// read the file line by line using scanner
	scanner := bufio.NewScanner(f)

	for scanner.Scan() {
		fmt.Printf("Selected Download URL : %s\n", scanner.Text())
		client := grab.NewClient()
		req, _ := grab.NewRequest("./downloads", scanner.Text())
		req.NoResume = true

		// Start download
		fmt.Printf("Downloading :%v...\n", req.URL())
		resp := client.Do(req)
		fmt.Printf("  %v\n", resp.HTTPResponse.Status)

		// start UI loop
		ticker := time.NewTicker(5000 * time.Millisecond)
		defer ticker.Stop()

	Loop:
		for {
			select {
			case <-ticker.C:
				fmt.Printf("  Transferred %v / %v (%.2f%%) / Elapsed Time %v /  ETA %v\n",
					convertByteSize(resp.BytesComplete()),
					convertByteSize(resp.Size()),
					100*resp.Progress(),
					resp.Duration(),
					resp.ETA())

			case <-resp.Done:
				break Loop
			}
		}

		// check for errors
		if err := resp.Err(); err != nil {
			fmt.Fprintf(os.Stderr, "Download failed: %v\n", err)
			os.Exit(1)
		}

		fmt.Printf("Download saved to ./%v \n", resp.Filename)
	}

	if err := scanner.Err(); err != nil {
		log.Fatal(err)
	}
}

func convertByteSize(b int64) string {
	bf := float64(b)
	for _, unit := range []string{" ", " Ki", " Mi", " Gi", " Ti", " Pi", " Ei", " Zi"} {
		if math.Abs(bf) < 1024.0 {
			return fmt.Sprintf("%3.1f%sB", bf, unit)
		}
		bf /= 1024.0
	}
	return fmt.Sprintf("%.1fYiB", bf)
}
