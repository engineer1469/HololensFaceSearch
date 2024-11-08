#pragma once

#include <map>
#include <chrono>
#include <thread>
#include <shared_mutex>
#include <ppltasks.h>
#include <vector>

namespace HolographicFaceTracker
{
    // Define TrackedFace at namespace scope
    struct TrackedFace
    {
        Windows::Graphics::Imaging::BitmapBounds FaceBox;
        std::chrono::steady_clock::time_point StartTime;
        bool ImageCaptured;
    };

    class VideoFrameProcessor;

    // Class to manage the FaceAnalysis::FaceTracker object and process video frames from
    // media capture using the VideoFrameProcessor class
    class FaceTrackerProcessor
    {
    public:
        static concurrency::task<std::shared_ptr<FaceTrackerProcessor>> CreateAsync(
            std::shared_ptr<VideoFrameProcessor> processor);

        FaceTrackerProcessor(
            Windows::Media::FaceAnalysis::FaceTracker^ tracker,
            std::shared_ptr<VideoFrameProcessor> processor);

        ~FaceTrackerProcessor(void);

        bool IsTrackingFaces(void) const;
        std::vector<Windows::Graphics::Imaging::BitmapBounds> GetLatestFaces(void) const;

    protected:
        void ProcessFrame(void);

        // Added methods
        void CaptureFaceImage(const TrackedFace& face);
        void SendImageOverTcp(const std::vector<unsigned char>& imageBytes);
        float ComputeIoU(
            Windows::Graphics::Imaging::BitmapBounds const& rectA,
            Windows::Graphics::Imaging::BitmapBounds const& rectB);

        // Map to track faces by a unique identifier
        std::map<unsigned int, TrackedFace> m_trackedFaces;

        // The duration a face must be looked at before capturing, in seconds
        const double m_captureThreshold = 3.0; // Replace with desired duration

        // Hostname and port of the laptop (replace with actual values)
        Platform::String^ m_serverHost;
        Platform::String^ m_serverPort;

        Windows::Media::FaceAnalysis::FaceTracker^ m_faceTracker;
        std::shared_ptr<VideoFrameProcessor>                  m_videoProcessor;

        mutable std::shared_mutex                             m_propertiesLock;
        std::vector<Windows::Graphics::Imaging::BitmapBounds> m_latestFaces;

        uint32_t                                              m_numFramesWithoutFaces = 0;

        std::thread                                           m_workerThread;
        bool                                                  m_isRunning = false;
    };
}
