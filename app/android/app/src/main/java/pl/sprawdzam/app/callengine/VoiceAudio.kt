package pl.sprawdzam.app.callengine

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.util.Log
import java.util.ArrayDeque
import kotlin.concurrent.thread

/**
 * Full-duplex call audio: AudioRecord (VOICE_COMMUNICATION, 16 kHz mono PCM16) -> 20 ms frames -> onFrame;
 * frames from the call socket -> jitter queue (60 ms prebuffer; above 300 ms quiet frames are skipped to catch up; 3 s hard cap) -> AudioTrack
 * (USAGE_VOICE_COMMUNICATION). Same behaviour as the HarmonyOS VoiceAudio.
 *
 * Speakerphone: the senior's phone usually lies on the table next to the caller's, so the call runs in
 * MODE_IN_COMMUNICATION on the built-in speaker, with the platform echo canceller and noise suppressor
 * attached to the capture session when the device has them (the VOICE_COMMUNICATION source already enables
 * the vendor AEC on most phones; the explicit effects make it deterministic).
 */
class VoiceAudio(context: Context) {
  private val audioManager = context.getSystemService(AudioManager::class.java)
  private var savedMode = AudioManager.MODE_NORMAL
  private var savedSpeaker = false
  private var effects: List<android.media.audiofx.AudioEffect> = emptyList()
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
  private var skipped = 0

  val stats: String
    get() = "framesOut=$framesOut framesIn=$framesIn skippedQuiet=$skipped dropped=$dropped"

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
    enterCommunicationMode()
    effects = attachEffects(rec.audioSessionId)
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
      // Short silence chunks while waiting for audio, so an underrun adds at most ~5 ms of extra latency
      // (a whole 20 ms silence frame per underrun made the queue overflow and drop audio on bursty input).
      val silence = ByteArray(SILENCE_BYTES)
      while (running) {
        val next = synchronized(lock) {
          if (buffering && queuedBytes < PREBUFFER_BYTES) {
            null
          } else {
            buffering = false
            var f = queue.pollFirst()
            // Behind by more than the target latency (bursty network or a voice prompt pushed faster than
            // real time): catch up by skipping quiet frames only, so no speech is lost.
            while (f != null && queuedBytes - f.size > TARGET_QUEUED_BYTES && isQuiet(f)) {
              queuedBytes -= f.size
              skipped++
              f = queue.pollFirst()
            }
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

  /** Queues one frame of caller audio for playback (drops the oldest beyond 3 s). */
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
    effects.forEach { runCatching { it.release() } }
    effects = emptyList()
    leaveCommunicationMode()
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

  private fun isQuiet(frame: ByteArray): Boolean {
    var i = 0
    while (i + 1 < frame.size) {
      val v = (frame[i].toInt() and 0xFF) or (frame[i + 1].toInt() shl 8)
      if (v > QUIET_PEAK || v < -QUIET_PEAK) return false
      i += 2
    }
    return true
  }

  private fun enterCommunicationMode() {
    runCatching {
      savedMode = audioManager.mode
      @Suppress("DEPRECATION")
      savedSpeaker = audioManager.isSpeakerphoneOn
      audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
      if (Build.VERSION.SDK_INT >= 31) {
        val speaker = audioManager.availableCommunicationDevices.firstOrNull {
          it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
        }
        val ok = speaker != null && audioManager.setCommunicationDevice(speaker)
        Log.i(TAG, "audio: speakerphone ${if (ok) "on" else "unavailable"}")
      } else {
        @Suppress("DEPRECATION")
        audioManager.isSpeakerphoneOn = true
      }
    }.onFailure { Log.w(TAG, "audio: cannot switch to speakerphone: ${it.message}") }
  }

  private fun leaveCommunicationMode() {
    runCatching {
      if (Build.VERSION.SDK_INT >= 31) {
        audioManager.clearCommunicationDevice()
      } else {
        @Suppress("DEPRECATION")
        audioManager.isSpeakerphoneOn = savedSpeaker
      }
      audioManager.mode = savedMode
    }
  }

  private fun attachEffects(sessionId: Int): List<android.media.audiofx.AudioEffect> {
    val out = mutableListOf<android.media.audiofx.AudioEffect>()
    val names = mutableListOf<String>()
    if (AcousticEchoCanceler.isAvailable()) {
      runCatching { AcousticEchoCanceler.create(sessionId) }.getOrNull()?.let {
        it.enabled = true
        out += it
        names += "AEC"
      }
    }
    if (NoiseSuppressor.isAvailable()) {
      runCatching { NoiseSuppressor.create(sessionId) }.getOrNull()?.let {
        it.enabled = true
        out += it
        names += "NS"
      }
    }
    Log.i(TAG, "audio: effects ${if (names.isEmpty()) "none available" else names.joinToString("+")}")
    return out
  }

  companion object {
    private const val TAG = "CallEngine"
    private const val PREBUFFER_BYTES = Protocol.FRAME_BYTES * 3
    private const val TARGET_QUEUED_BYTES = Protocol.FRAME_BYTES * 15 // 300 ms
    private const val MAX_QUEUED_BYTES = Protocol.FRAME_BYTES * 150 // 3 s hard cap
    private const val QUIET_PEAK = 600 // PCM16 peak below which a frame counts as silence
    private const val SILENCE_BYTES = 160 // 5 ms
  }
}
