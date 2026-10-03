package pl.sprawdzam.app.callengine

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.util.Log
import java.util.ArrayDeque
import kotlin.concurrent.thread

/**
 * Full-duplex call audio: AudioRecord (VOICE_COMMUNICATION, 16 kHz mono PCM16) -> 20 ms frames -> onFrame;
 * frames from the call socket -> bounded jitter queue (60 ms prebuffer, 200 ms cap) -> AudioTrack
 * (USAGE_VOICE_COMMUNICATION). Same behaviour as the HarmonyOS VoiceAudio.
 */
class VoiceAudio {
  private val lock = Object()
  private val queue = ArrayDeque<ByteArray>()
  private var queuedBytes = 0
  private var buffering = true
  @Volatile private var running = false
  @Volatile var muted = false
  private var record: AudioRecord? = null
  private var track: AudioTrack? = null
  private var framesOut = 0
  private var framesIn = 0
  private var dropped = 0

  val stats: String
    get() = "framesOut=$framesOut framesIn=$framesIn dropped=$dropped"

  /** Requires RECORD_AUDIO (checked by the module before accept). */
  @SuppressLint("MissingPermission")
  fun start(onFrame: (ByteArray) -> Unit) {
    if (running) return
    running = true
    muted = false
    val minRec = AudioRecord.getMinBufferSize(
        Protocol.SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
    val rec = AudioRecord(
        MediaRecorder.AudioSource.VOICE_COMMUNICATION,
        Protocol.SAMPLE_RATE,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT,
        maxOf(minRec, Protocol.FRAME_BYTES * 4))
    val minPlay = AudioTrack.getMinBufferSize(
        Protocol.SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
    val trk = AudioTrack.Builder()
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build())
        .setAudioFormat(
            AudioFormat.Builder()
                .setSampleRate(Protocol.SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .build())
        .setBufferSizeInBytes(maxOf(minPlay, Protocol.FRAME_BYTES * 4))
        .setTransferMode(AudioTrack.MODE_STREAM)
        .build()
    record = rec
    track = trk
    rec.startRecording()
    trk.play()

    thread(name = "sprawdzam-capture") {
      val frame = ByteArray(Protocol.FRAME_BYTES)
      while (running) {
        var filled = 0
        while (running && filled < frame.size) {
          val n = rec.read(frame, filled, frame.size - filled)
          if (n <= 0) break
          filled += n
        }
        if (!running || filled < frame.size) continue
        framesOut++
        onFrame(if (muted) ByteArray(Protocol.FRAME_BYTES) else frame.copyOf())
      }
    }
    thread(name = "sprawdzam-playback") {
      val silence = ByteArray(Protocol.FRAME_BYTES)
      while (running) {
        val next = synchronized(lock) {
          if (buffering && queuedBytes < PREBUFFER_BYTES) {
            null
          } else {
            buffering = false
            val f = queue.pollFirst()
            if (f == null) {
              buffering = true
            } else {
              queuedBytes -= f.size
            }
            f
          }
        }
        trk.write(next ?: silence, 0, (next ?: silence).size) // blocking write paces the loop
      }
    }
    Log.i(TAG, "audio started")
  }

  /** Queues one frame of caller audio for playback (drops the oldest beyond 200 ms). */
  fun play(frame: ByteArray) {
    synchronized(lock) {
      framesIn++
      queue.addLast(frame)
      queuedBytes += frame.size
      while (queuedBytes > MAX_QUEUED_BYTES && queue.size > 1) {
        queuedBytes -= queue.removeFirst().size
        dropped++
      }
    }
  }

  fun stop() {
    if (!running) return
    running = false
    runCatching { record?.stop() }
    runCatching { record?.release() }
    runCatching { track?.stop() }
    runCatching { track?.release() }
    record = null
    track = null
    synchronized(lock) {
      queue.clear()
      queuedBytes = 0
      buffering = true
    }
    Log.i(TAG, "audio stopped ($stats)")
  }

  companion object {
    private const val TAG = "CallEngine"
    private const val PREBUFFER_BYTES = Protocol.FRAME_BYTES * 3
    private const val MAX_QUEUED_BYTES = Protocol.FRAME_BYTES * 10
  }
}
