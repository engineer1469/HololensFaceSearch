#include "pch.h"
#include "FaceTrackerProcessor.h"
#include "VideoFrameProcessor.h"

#include <agile.h>
#include <ppltasks.h>
#include <collection.h>
#include <Windows.Foundation.h>
#include <Windows.Graphics.Imaging.h>
#include <Windows.Media.h>
#include <Windows.Media.Capture.h>
#include <Windows.Media.Capture.Frames.h>
#include <Windows.Media.FaceAnalysis.h>
#include <Windows.Networking.h>
#include <Windows.Networking.Sockets.h>
#include <Windows.Storage.Streams.h>
#include <windows.h> // For OutputDebugString

using namespace HolographicFaceTracker;

using namespace Platform;
using namespace Windows::Foundation::Collections;
using namespace Windows::Foundation::Numerics;
using namespace Windows::Graphics::Imaging;
using namespace Windows::Media;
using namespace Windows::Media::Capture;
using namespace Windows::Media::Capture::Frames;
using namespace Windows::Media::FaceAnalysis;
using namespace Windows::Networking;
using namespace Windows::Networking::Sockets;
using namespace Windows::Storage::Streams;

using namespace Concurrency;

FaceTrackerProcessor::FaceTrackerProcessor(FaceTracker^ tracker, std::shared_ptr<VideoFrameProcessor> processor)
    : m_faceTracker(std::move(tracker))
    , m_videoProcessor(std::move(processor))
    , m_serverHost(ref new Platform::String(L"192.168.1.66")) // Replace with your laptop's IP address
    , m_serverPort(ref new Platform::String(L"12345"))          // Replace with your laptop's port
{
    if (m_videoProcessor)
    {
        // Create background thread for FaceTrackingProcessing
        m_workerThread = std::thread([this]
            {
                m_isRunning = true;

                while (m_isRunning)
                {
                    ProcessFrame();
                }
            });
    }
}

FaceTrackerProcessor::~FaceTrackerProcessor(void)
{
    m_isRunning = false;
    if (m_workerThread.joinable())
    {
        m_workerThread.join();
    }
}

task<std::shared_ptr<FaceTrackerProcessor>> FaceTrackerProcessor::CreateAsync(std::shared_ptr<VideoFrameProcessor> processor)
{
    return create_task(FaceTracker::CreateAsync())
        .then([=](FaceTracker^ tracker)
            {
                tracker->MinDetectableFaceSize = BitmapSize{ 64u, 64u };
                tracker->MaxDetectableFaceSize = BitmapSize{ 512u, 512u };

                return std::make_shared<FaceTrackerProcessor>(std::move(tracker), std::move(processor));
            });
}

bool FaceTrackerProcessor::IsTrackingFaces(void) const
{
    auto lock = std::shared_lock<std::shared_mutex>(m_propertiesLock);
    return !m_latestFaces.empty();
}

std::vector<BitmapBounds> FaceTrackerProcessor::GetLatestFaces(void) const
{
    auto lock = std::shared_lock<std::shared_mutex>(m_propertiesLock);
    return m_latestFaces;
}

void FaceTrackerProcessor::ProcessFrame(void)
{
    if (MediaFrameReference^ frame = m_videoProcessor->GetLatestFrame())
    {
        if (VideoMediaFrame^ videoMediaFrame = frame->VideoMediaFrame)
        {
            // Validate that the incoming frame format is compatible with the FaceTracker
            if (videoMediaFrame->SoftwareBitmap && FaceTracker::IsBitmapPixelFormatSupported(videoMediaFrame->SoftwareBitmap->BitmapPixelFormat))
            {
                // Process the frame asynchronously
                task<IVector<DetectedFace^>^> processFrameTask = create_task(m_faceTracker->ProcessNextFrameAsync(videoMediaFrame->GetVideoFrame()));

                try
                {
                    IVector<DetectedFace^>^ faces = processFrameTask.get();

                    std::lock_guard<std::shared_mutex> lock(m_propertiesLock);

                    auto now = std::chrono::steady_clock::now();

                    // Temporary map for current faces
                    std::map<unsigned int, TrackedFace> currentFaces;

                    // Assign IDs to new faces
                    unsigned int faceId = 0;

                    for (DetectedFace^ detectedFace : faces)
                    {
                        BitmapBounds faceBox = detectedFace->FaceBox;

                        // Try to find a matching face in m_trackedFaces
                        bool matched = false;
                        unsigned int matchedId = 0;

                        for (auto& pair : m_trackedFaces)
                        {
                            unsigned int existingFaceId = pair.first;
                            TrackedFace& existingFace = pair.second;

                            // Compute IoU between faceBox and existingFace.FaceBox
                            float iou = ComputeIoU(faceBox, existingFace.FaceBox);

                            if (iou > 0.5f) // Threshold for matching
                            {
                                matched = true;
                                matchedId = existingFaceId;
                                break;
                            }
                        }

                        if (matched)
                        {
                            // Update existing face
                            TrackedFace& existingFace = m_trackedFaces[matchedId];
                            existingFace.FaceBox = faceBox;

                            // Check if image has already been captured
                            if (!existingFace.ImageCaptured)
                            {
                                auto duration = std::chrono::duration<double>(now - existingFace.StartTime).count();
                                if (duration >= m_captureThreshold)
                                {
                                    // Capture face image
                                    CaptureFaceImage(existingFace);

                                    existingFace.ImageCaptured = true;
                                }
                            }

                            // Add to currentFaces
                            currentFaces[matchedId] = existingFace;
                        }
                        else
                        {
                            // Add new face
                            TrackedFace newFace;
                            newFace.FaceBox = faceBox;
                            newFace.StartTime = now;
                            newFace.ImageCaptured = false;

                            currentFaces[faceId] = newFace;
                            faceId++;
                        }
                    }

                    // Update m_trackedFaces
                    m_trackedFaces = currentFaces;

                    // Update m_latestFaces for rendering
                    m_latestFaces.resize(faces->Size);
                    for (uint32_t i = 0u; i < faces->Size; ++i)
                    {
                        m_latestFaces[i] = faces->GetAt(i)->FaceBox;
                    }
                }
                catch (task_canceled const&)
                {
                    // The task might be cancelled if the FaceAnalysis failed.
                    return;
                }
            }
        }
    }
}

float FaceTrackerProcessor::ComputeIoU(BitmapBounds const& rectA, BitmapBounds const& rectB)
{
    uint32_t xA = max(rectA.X, rectB.X);
    uint32_t yA = max(rectA.Y, rectB.Y);
    uint32_t xB = min(rectA.X + rectA.Width, rectB.X + rectB.Width);
    uint32_t yB = min(rectA.Y + rectA.Height, rectB.Y + rectB.Height);

    if (xA >= xB || yA >= yB)
    {
        return 0.0f;
    }

    uint32_t interArea = (xB - xA) * (yB - yA);

    uint32_t boxAArea = rectA.Width * rectA.Height;
    uint32_t boxBArea = rectB.Width * rectB.Height;

    float iou = static_cast<float>(interArea) / static_cast<float>(boxAArea + boxBArea - interArea);
    return iou;
}

void FaceTrackerProcessor::CaptureFaceImage(const TrackedFace& face)
{
    // Get the latest frame
    if (MediaFrameReference^ frame = m_videoProcessor->GetLatestFrame())
    {
        if (VideoMediaFrame^ videoMediaFrame = frame->VideoMediaFrame)
        {
            SoftwareBitmap^ softwareBitmap = videoMediaFrame->SoftwareBitmap;

            if (softwareBitmap)
            {
                // Ensure bounds are within the bitmap dimensions
                BitmapBounds adjustedBounds = face.FaceBox;
                adjustedBounds.X = min(adjustedBounds.X, static_cast<UINT32>(softwareBitmap->PixelWidth - 1));
                adjustedBounds.Y = min(adjustedBounds.Y, static_cast<UINT32>(softwareBitmap->PixelHeight - 1));
                adjustedBounds.Width = min(adjustedBounds.Width, static_cast<UINT32>(softwareBitmap->PixelWidth - adjustedBounds.X));
                adjustedBounds.Height = min(adjustedBounds.Height, static_cast<UINT32>(softwareBitmap->PixelHeight - adjustedBounds.Y));

                // Encode to JPEG
                create_task([this, softwareBitmap, adjustedBounds]()
                    {
                        // Convert the bitmap to a format supported by the encoder
                        SoftwareBitmap^ convertedBitmap = SoftwareBitmap::Convert(softwareBitmap, BitmapPixelFormat::Bgra8);

                        InMemoryRandomAccessStream^ stream = ref new InMemoryRandomAccessStream();
                        return create_task(BitmapEncoder::CreateAsync(BitmapEncoder::JpegEncoderId, stream))
                            .then([this, convertedBitmap, adjustedBounds, stream](BitmapEncoder^ encoder)
                                {
                                    encoder->SetSoftwareBitmap(convertedBitmap);

                                    // Set crop bounds
                                    encoder->BitmapTransform->Bounds = adjustedBounds;

                                    return encoder->FlushAsync();
                                })
                            .then([this, stream]()
                                {
                                    // Read stream into byte array
                                    stream->Seek(0);
                                    DataReader^ reader = ref new DataReader(stream->GetInputStreamAt(0));
                                    return create_task(reader->LoadAsync(static_cast<UINT32>(stream->Size)))
                                        .then([this, reader](UINT32 bytesLoaded)
                                            {
                                                Platform::Array<unsigned char>^ buffer = ref new Platform::Array<unsigned char>(bytesLoaded);
                                                reader->ReadBytes(buffer);

                                                std::vector<unsigned char> imageBytes(buffer->Data, buffer->Data + buffer->Length);

                                                // Send over TCP
                                                SendImageOverTcp(imageBytes);
                                            });
                                });
                    });
            }
        }
    }
}



void FaceTrackerProcessor::SendImageOverTcp(const std::vector<unsigned char>& imageBytes)
{
    // Create the StreamSocket
    auto socket = ref new StreamSocket();

    // Create an agile reference to the socket
    Platform::Agile<StreamSocket^> agileSocket(socket);

    create_task(socket->ConnectAsync(ref new HostName(m_serverHost), m_serverPort))
        .then([this, agileSocket, imageBytes](task<void> previousTask)
            {
                try
                {
                    previousTask.get(); // Check for exceptions

                    // Access the socket via the agile reference
                    auto socketRef = agileSocket.Get();

                    auto outputStream = socketRef->OutputStream;
                    auto writer = ref new DataWriter(outputStream);

                    // Write the size of the image first (optional)
                    writer->WriteUInt32(static_cast<UINT32>(imageBytes.size()));

                    // Create Platform::Array and copy data
                    unsigned int dataSize = static_cast<unsigned int>(imageBytes.size());
                    Platform::Array<unsigned char>^ bufferArray = ref new Platform::Array<unsigned char>(dataSize);

                    if (dataSize > 0)
                    {
                        memcpy(bufferArray->Data, imageBytes.data(), dataSize);
                    }

                    // Write the image bytes
                    writer->WriteBytes(bufferArray);

                    // Store the data asynchronously
                    return create_task(writer->StoreAsync());
                }
                catch (Platform::Exception^ ex)
                {
                    OutputDebugString(L"Failed to connect or send data over TCP (first lambda).\n");

                    // Clean up
                    auto socketRef = agileSocket.Get();
                    if (socketRef != nullptr)
                    {
                        delete socketRef;
                    }
                    return task_from_result<unsigned int>(0);
                }
            })
        .then([agileSocket](task<unsigned int> previousTask)
            {
                try
                {
                    unsigned int bytesStored = previousTask.get(); // Check for exceptions
                    // Data sent successfully
                    OutputDebugString(L"Data sent successfully.\n");
                }
                catch (Platform::Exception^ ex)
                {
                    OutputDebugString(L"Failed to send data over TCP (second lambda).\n");
                }

                // Clean up
                auto socketRef = agileSocket.Get();
                if (socketRef != nullptr)
                {
                    delete socketRef;
                }
            });
}