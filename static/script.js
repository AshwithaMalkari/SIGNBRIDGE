// Import Three.js, GLTFLoader, and defaultPose via the import map
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { defaultPose } from './Animations/defaultPose.js';

document.addEventListener('DOMContentLoaded', () => {
  // Element selectors
  const micButton = document.getElementById('micButton');
  const textSubmitButton = document.getElementById('textSubmitButton');
  const textInput = document.getElementById('textInput');
  const transcriptField = document.getElementById('transcript');
  const islBox = document.getElementById('islBox');
  const processedTextField = document.getElementById('processed-text');
  const animationContainer = document.getElementById('animationContainer');
  const historyPanel = document.getElementById('history-panel');
  const speedSlider = document.getElementById('speedSlider');
  const speedValue = document.getElementById('speedValue');
  const inputTitle = document.getElementById('input-title');
  const tabButtons = document.querySelectorAll('.tab-button');

  // Global state for the animation system
  const state = {
    text: '',
    bot: 'ybot',
    speed: 0.1,
    baseSpeed: 0.1,
    speedMultiplier: 1.0,
    pause: 800,
    listening: false,
    animations: [],
    scene: null,
    camera: null,
    renderer: null,
    avatar: null,
    flag: false,
    pending: false,
    textTimer: false,
    characters: [],
    alphabetModules: {},
    wordModules: {},
    numberModules: {},
    wordList: [],
    numberList: ['0','1','2','3','4','5','6','7','8','9'],
    currentInputMode: 'sign'
  };

  let recognition = null;
  let isRecording = false;

  // Initialize Speech Recognition safely
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.warn("Speech recognition not supported in this browser!");
    if (micButton) micButton.disabled = true;
  } else {
    try {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";
    } catch (e) {
      console.warn("SpeechRecognition init error:", e);
    }
  }

  // -------------------------
  // Tab Switching Functionality
  // -------------------------
  function switchToVoiceInput() {
    state.currentInputMode = 'voice';
    if (window.stopSignRecognition) {
      window.stopSignRecognition();
    }
    const signPanel = document.getElementById('signInputPanel');
    const voicePanel = document.getElementById('voiceInputPanel');
    const textPanel = document.getElementById('textInputPanel');
    if (signPanel) signPanel.style.display = 'none';
    if (voicePanel) voicePanel.style.display = 'block';
    if (textPanel) textPanel.style.display = 'none';

    document.querySelectorAll('.tab-button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === 'voice');
    });
    const mobVoice = document.getElementById('mobileNavVoice');
    if (mobVoice) mobVoice.classList.add('active');
    ['mobileNavSign', 'mobileNavText'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('active');
    });
    if (window.feather) feather.replace();
    setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
  }

  function switchToTextInput() {
    state.currentInputMode = 'text';
    if (window.stopSignRecognition) {
      window.stopSignRecognition();
    }
    if (isRecording) {
      stopRecording();
    }
    const signPanel = document.getElementById('signInputPanel');
    const voicePanel = document.getElementById('voiceInputPanel');
    const textPanel = document.getElementById('textInputPanel');
    if (signPanel) signPanel.style.display = 'none';
    if (voicePanel) voicePanel.style.display = 'none';
    if (textPanel) textPanel.style.display = 'block';

    document.querySelectorAll('.tab-button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === 'text');
    });
    const mobText = document.getElementById('mobileNavText');
    if (mobText) mobText.classList.add('active');
    ['mobileNavSign', 'mobileNavVoice'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('active');
    });
    if (window.feather) feather.replace();
    setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
  }

  function switchToSignInput() {
    state.currentInputMode = 'sign';
    if (isRecording) {
      stopRecording();
    }
    const signPanel = document.getElementById('signInputPanel');
    const voicePanel = document.getElementById('voiceInputPanel');
    const textPanel = document.getElementById('textInputPanel');
    if (signPanel) signPanel.style.display = 'block';
    if (voicePanel) voicePanel.style.display = 'none';
    if (textPanel) textPanel.style.display = 'none';

    document.querySelectorAll('.tab-button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === 'sign');
    });
    const mobSign = document.getElementById('mobileNavSign');
    if (mobSign) mobSign.classList.add('active');
    ['mobileNavVoice', 'mobileNavText'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('active');
    });
    if (window.feather) feather.replace();
    setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
  }

  window.switchToVoiceInput = switchToVoiceInput;
  window.switchToTextInput = switchToTextInput;
  window.switchToSignInput = switchToSignInput;

  // Set up tab event listeners
  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      tabButtons.forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      
      if (button.dataset.tab === 'voice') {
        switchToVoiceInput();
      } else if (button.dataset.tab === 'text') {
        switchToTextInput();
      } else if (button.dataset.tab === 'sign') {
        switchToSignInput();
      }
    });
  });

  // -------------------------
  // Text Input Handling
  // -------------------------
  function handleTextSubmit() {
    const text = textInput ? textInput.value.trim() : '';
    if (text) {
      if (transcriptField) transcriptField.value = text;
      sendTextForProcessing(text);
    } else {
      alert('Please enter some text to translate');
    }
  }

  if (textSubmitButton) {
    textSubmitButton.addEventListener('click', handleTextSubmit);
  }

  if (textInput) {
    textInput.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleTextSubmit();
      }
    });
  }

  // Voice & Text Clear and Action buttons
  const voiceClearButton = document.getElementById('voiceClearButton');
  const textClearButton = document.getElementById('textClearButton');
  const voiceTranslateButton = document.getElementById('voiceTranslateButton');
  const clearBtn = document.getElementById('clearButton');

  if (voiceClearButton) {
    voiceClearButton.addEventListener('click', () => {
      if (transcriptField) transcriptField.value = '';
      if (islBox) islBox.innerHTML = '';
      if (processedTextField) processedTextField.value = '';
    });
  }

  if (textClearButton) {
    textClearButton.addEventListener('click', () => {
      if (textInput) textInput.value = '';
      if (islBox) islBox.innerHTML = '';
      if (processedTextField) processedTextField.value = '';
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (transcriptField) transcriptField.value = '';
      if (textInput) textInput.value = '';
      if (islBox) islBox.innerHTML = '';
      if (processedTextField) processedTextField.value = '';
    });
  }

  if (voiceTranslateButton) {
    voiceTranslateButton.addEventListener('click', () => {
      const text = (transcriptField ? transcriptField.value : '').trim();
      if (text) {
        sendTextForProcessing(text);
      } else {
        alert('Please record some speech first by clicking Start Recording.');
      }
    });
  }

  // Speed Slider Handler
  if (speedSlider) {
    if (speedValue) speedValue.textContent = `${speedSlider.value}x`;
    speedSlider.addEventListener('input', () => {
      const multiplier = parseFloat(speedSlider.value);
      state.speedMultiplier = multiplier;
      state.speed = state.baseSpeed * multiplier;
      if (speedValue) speedValue.textContent = `${multiplier.toFixed(1)}x`;
    });
  }

  // Speech Recognition Methods
  const startRecording = () => {
    state.currentInputMode = 'voice';
    if (!recognition) {
      alert("Speech recognition is not supported or permitted in this browser. Please use Chrome on Android/Desktop or type in Text Input.");
      return;
    }
    try {
      console.log("Starting speech recognition");
      recognition.start();
      isRecording = true;
    } catch (e) {
      console.warn("Recognition start notice:", e);
    }
  };

  const stopRecording = () => {
    if (!recognition) return;
    try {
      console.log("Stopping speech recognition");
      recognition.stop();
    } catch (e) {}
    isRecording = false;
    if (micButton) {
      micButton.innerHTML = '<i data-feather="mic"></i> Start Recording';
      micButton.classList.remove('recording');
      if (window.feather) feather.replace();
    }
  };

  // -------------------------
  // 3D Animation System Setup
  // -------------------------
  state.animate = function() {
    requestAnimationFrame(this.animate.bind(this));
    if (!this.scene || !this.camera || !this.renderer) {
      return;
    }
    this.renderer.render(this.scene, this.camera);

    if (!this.avatar || this.animations.length === 0) return;

    const currentAnim = this.animations[0];

    if (currentAnim && currentAnim.length) {
      if (!this.flag) {
        if (currentAnim[0] === 'add-text') {
          addTextStep(currentAnim);
          return;
        } else {
          processBoneAnimation(currentAnim, this);
        }
      }
    } else {
      if (!this.flag) {
        this.flag = true;
        setTimeout(() => {
          this.flag = false;
          this.animations.shift();
        }, this.pause / this.speedMultiplier);
      }
    }
  };

  function addTextStep(animCommand) {
    if (!state.textTimer) {
      if (processedTextField) {
        if ('value' in processedTextField) {
          processedTextField.value += animCommand[1];
        } else {
          processedTextField.textContent += animCommand[1];
        }
      }
      state.textTimer = true;
      setTimeout(() => {
        state.textTimer = false;
        state.animations.shift();
      }, 100 / state.speedMultiplier);
    }
  }

  function processBoneAnimation(animSteps, ctx) {
    for (let i = 0; i < animSteps.length;) {
      const [boneName, action, axis, limit, sign] = animSteps[i];
      let bone = ctx.avatar.getObjectByName(boneName);
      if (!bone && boneName.startsWith('mixamorig')) {
        const altName = boneName.includes(':')
          ? boneName.replace('mixamorig:', 'mixamorig')
          : boneName.replace(/^mixamorig/, 'mixamorig:');
        bone = ctx.avatar.getObjectByName(altName);
      }
      if (bone) {
        if (sign === '+' && bone[action][axis] < limit) {
          bone[action][axis] = Math.min(bone[action][axis] + ctx.speed, limit);
          i++;
        } else if (sign === '-' && bone[action][axis] > limit) {
          bone[action][axis] = Math.max(bone[action][axis] - ctx.speed, limit);
          i++;
        } else {
          animSteps.splice(i, 1);
        }
      } else {
        animSteps.splice(i, 1);
      }
    }
  }

  // -------------------------
  // History Management
  // -------------------------
  const saveToHistory = (originalText, islText) => {
    fetch("/save_history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ original_text: originalText, isl_text: islText })
    })
      .then(response => response.json())
      .catch(error => console.error("History save error:", error));
  };

  const displayHistory = () => {
    fetch("/get_history")
      .then(response => response.json())
      .then(history => {
        const historyList = document.getElementById('history-list');
        if (!historyList) return;
        historyList.innerHTML = '';
        if (history.length === 0) {
          historyList.innerHTML = '<p class="empty-history">No conversion history yet.</p>';
          return;
        }
        history.reverse().forEach(item => {
          const historyItem = document.createElement('div');
          historyItem.className = 'history-item';
          historyItem.innerHTML = `
            <div class="history-content">
              <div class="original-text">${item.original_text}</div>
              <div class="isl-text">${item.isl_text}</div>
              <div class="timestamp">${item.timestamp}</div>
            </div>
            <button class="delete-btn" data-id="${item._id}">
              <i data-feather="trash-2"></i>
            </button>
          `;
          historyList.appendChild(historyItem);
        });
        if (window.feather) feather.replace();
      })
      .catch(error => console.error("History fetch error:", error));
  };

  // -------------------------
  // Dynamic Module Loaders
  // -------------------------
  function getAnimationFunction(moduleObj, key) {
    if (moduleObj[key] && typeof moduleObj[key] === 'function') return moduleObj[key];
    if (moduleObj.default && typeof moduleObj.default === 'function') return moduleObj.default;
    for (const exportName in moduleObj) {
      if (typeof moduleObj[exportName] === 'function') return moduleObj[exportName];
    }
    return null;
  }

  const loadAlphabetModules = async () => {
    const alphabetChars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const promises = alphabetChars.split('').map(async char => {
      try {
        const moduleObj = await import(`./Animations/Alphabets/${char}.js`);
        const animationFunction = getAnimationFunction(moduleObj, char);
        if (animationFunction) state.alphabetModules[char] = animationFunction;
      } catch (error) {
        // Quietly handle missing animations
      }
    });
    await Promise.allSettled(promises);
  };

  const loadWordModules = async () => {
    const commonWords = ['HOME', 'TIME', 'YOU', 'PERSON'];
    const promises = commonWords.map(async word => {
      try {
        const moduleObj = await import(`./Animations/Words/${word.toUpperCase()}.js`);
        const animationFunction = getAnimationFunction(moduleObj, word);
        if (animationFunction) {
          state.wordModules[word] = animationFunction;
          state.wordList.push(word);
        }
      } catch (error) {}
    });
    await Promise.allSettled(promises);
  };

  const loadNumberModules = async () => {
    const numbers = '0123456789';
    const promises = numbers.split('').map(async num => {
      try {
        const moduleObj = await import(`./Animations/Numbers/${num}.js`);
        const animationFunction = getAnimationFunction(moduleObj, num);
        if (animationFunction) state.numberModules[num] = animationFunction;
      } catch (error) {}
    });
    await Promise.allSettled(promises);
  };

  // -------------------------
  // Three.js Initialization
  // -------------------------
  function initThree() {
    if (!animationContainer) return false;
    animationContainer.innerHTML = '';
    state.scene = new THREE.Scene();
    state.scene.background = new THREE.Color(0xffffff); // Standard clean studio background
    
    const w = animationContainer.clientWidth || 360;
    const h = animationContainer.clientHeight || 280;

    state.camera = new THREE.PerspectiveCamera(
      30,
      w / h,
      0.1,
      1000
    );
    state.camera.position.set(0, 1.6, 1.5);
    state.camera.lookAt(0, 1.4, 0);
    
    state.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    state.renderer.setPixelRatio(window.devicePixelRatio || 1);
    state.renderer.shadowMap.enabled = true;
    state.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    state.renderer.setSize(w, h);
    animationContainer.appendChild(state.renderer.domElement);
  
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    state.scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.85);
    directionalLight.position.set(0, 3, 3);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 1024;
    directionalLight.shadow.mapSize.height = 1024;
    state.scene.add(directionalLight);
  
    return true;
  }
  
  function loadModel(modelPath) {
    return new Promise((resolve, reject) => {
      fetch(modelPath)
        .then(response => {
          if (!response.ok) throw new Error(`Model file not found: ${modelPath}`);
          const loader = new GLTFLoader();
          if (state.avatar) state.scene.remove(state.avatar);
          loader.load(
            modelPath,
            (gltf) => {
              gltf.scene.traverse((child) => {
                if (child.isMesh) {
                  child.frustumCulled = false;
                  child.castShadow = true;
                  child.receiveShadow = true;
                }
              });
              state.avatar = gltf.scene;
              state.scene.add(state.avatar);
              try {
                defaultPose(state);
                resolve();
              } catch (error) {
                console.warn("defaultPose notice:", error);
                resolve();
              }
            },
            undefined,
            (error) => reject(error)
          );
        })
        .catch(error => reject(error));
    });
  }
  
  // -------------------------
  // Processing Animation Commands
  // -------------------------
  window.processAnimation = processAnimation;
  function processAnimation(text) {
    if (!text) return;
    
    const processedText = text.toUpperCase()
      .replace(/\|/g, ' ')
      .replace(/ZERO/gi, '0')
      .replace(/ONE/gi, '1')
      .replace(/TWO/gi, '2')
      .replace(/THREE/gi, '3')
      .replace(/FOUR/gi, '4')
      .replace(/FIVE/gi, '5')
      .replace(/SIX/gi, '6')
      .replace(/SEVEN/gi, '7')
      .replace(/EIGHT/gi, '8')
      .replace(/NINE/gi, '9')
      .replace(/[^A-Z0-9\s]/g, ' ');
    
    const words = processedText.split(/\s+/).filter(w => w && w.trim() !== '');
    
    state.animations = [];
    state.characters = [];
    
    if (processedTextField) {
      if ('value' in processedTextField) processedTextField.value = '';
      else processedTextField.textContent = '';
    }

    words.forEach(word => {
      if (/^\d+$/.test(word)) {
        [...word].forEach(digit => {
          state.animations.push(['add-text', digit]);
          if (state.numberModules[digit]) state.numberModules[digit](state);
        });
        state.animations.push(['add-text', ' ']);
      }
      else if (state.wordList.includes(word)) {
        state.animations.push(['add-text', `${word} `]);
        if (state.wordModules[word]) state.wordModules[word](state);
      } 
      else {
        [...word].forEach((ch, i) => {
          const charText = (i === word.length - 1) ? `${ch} ` : ch;
          state.animations.push(['add-text', charText]);
          if (state.alphabetModules[ch]) state.alphabetModules[ch](state);
        });
      }
    });

    if (!state.pending && state.animations.length > 0) {
      state.pending = true;
      state.animate();
    }
  }

  // -------------------------
  // Sending Text for Processing
  // -------------------------
  window.sendTextForProcessing = sendTextForProcessing;
  window.formatISLStructure = formatISLStructure;

  function sendTextForProcessing(text) {
    if (!text) return;
    if (islBox) islBox.innerHTML = '<span class="loading">Translating to ISL...</span>';

    fetch("/save_text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    })
      .then(response => response.json())
      .then(data => {
        if (islBox) islBox.innerHTML = formatISLStructure(data.isl_structure);
        if (processedTextField) {
          if ('value' in processedTextField) processedTextField.value = data.isl_structure || "";
          else processedTextField.textContent = data.isl_structure || "";
        }
        saveToHistory(data.original_text, data.isl_structure);
        processAnimation(data.isl_structure);
        const animContainer = document.getElementById("animationContainer") || document.querySelector(".output-panel");
        if (animContainer) {
          animContainer.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      })
      .catch(error => {
        console.error("Processing error:", error);
        if (islBox) islBox.innerHTML = '<span class="error">Error processing text</span>';
      });
  }

  // -------------------------
  // Formatting ISL Structure
  // -------------------------
  function formatISLStructure(islText) {
    return islText.split('|')
      .map(sentence =>
        sentence.trim().split(' ')
          .map(word => `<span class="isl-word ${getWordClass(word)}">${word}</span>`)
          .join(' ')
      )
      .join('<span class="sentence-divider">|</span>');
  }

  function getWordClass(word) {
    if (/\d/.test(word)) return 'number';
    if (["what", "why", "how", "when", "where"].includes(word.toLowerCase())) return 'question';
    if (["not", "no"].includes(word.toLowerCase())) return 'negation';
    return '';
  }

  // -------------------------
  // Event Listeners for UI Actions (Safely Guarded)
  // -------------------------
  const historyBtn = document.getElementById('history-button');
  if (historyBtn && historyPanel) {
    historyBtn.addEventListener('click', () => {
      historyPanel.classList.add('show');
      displayHistory();
    });
  }

  const closeHistoryBtn = document.getElementById('close-history');
  if (closeHistoryBtn && historyPanel) {
    closeHistoryBtn.addEventListener('click', () => {
      historyPanel.classList.remove('show');
    });
  }

  const historyList = document.getElementById('history-list');
  if (historyList) {
    historyList.addEventListener('click', (e) => {
      const deleteBtn = e.target.closest('.delete-btn');
      if (deleteBtn) {
        const id = deleteBtn.dataset.id;
        if (confirm("Are you sure you want to delete this entry?")) {
          fetch(`/delete_history/${id}`, { method: "DELETE" })
            .then(response => response.json())
            .then(data => data.error ? alert(data.error) : displayHistory())
            .catch(error => console.error("Delete error:", error));
        }
      }
    });
  }

  const clearHistoryBtn = document.getElementById('clearHistoryButton');
  if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', () => {
      if (confirm("Are you sure you want to clear all conversion history?")) {
        fetch("/clear_history", { method: "DELETE" })
          .then(response => response.json())
          .then(data => data.error ? alert(data.error) : displayHistory())
          .catch(error => console.error("Clear error:", error));
      }
    });
  }

  if (micButton) {
    micButton.addEventListener('click', () => {
      isRecording ? stopRecording() : startRecording();
    });
  }

  // -------------------------
  // Speech Recognition Event Handlers
  // -------------------------
  if (recognition) {
    recognition.onstart = () => {
      isRecording = true;
      if (micButton) {
        micButton.innerHTML = '<i data-feather="mic-off"></i> Stop Recording';
        micButton.classList.add('recording');
        if (window.feather) feather.replace();
      }
    };

    recognition.onresult = (event) => {
      let interimTranscript = '';
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        let text = event.results[i][0].transcript;
        
        text = text
          .replace(/zero/gi, '0')
          .replace(/one/gi, '1')
          .replace(/two/gi, '2')
          .replace(/three/gi, '3')
          .replace(/four/gi, '4')
          .replace(/five/gi, '5')
          .replace(/six/gi, '6')
          .replace(/seven/gi, '7')
          .replace(/eight/gi, '8')
          .replace(/nine/gi, '9');
        
        event.results[i].isFinal ? finalTranscript += text : interimTranscript += text;
      }
      if (transcriptField) {
        transcriptField.value = finalTranscript + interimTranscript;
      }
      if (finalTranscript) sendTextForProcessing(finalTranscript);
    };

    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      stopRecording();
    };

    recognition.onend = () => {
      if (isRecording) {
        try { recognition.start(); } catch (e) {}
      }
    };
  }

  // -------------------------
  // Initialize 3D System and App
  // -------------------------
  async function init3DSystem() {
    try {
      console.log("Starting 3D System initialization...");
      if (!initThree()) throw new Error("Three.js initialization failed");
      
      // Load model FIRST so avatar renders immediately in default pose!
      console.log("Loading 3D avatar model...");
      await loadModel(`/static/Models/${state.bot}/${state.bot}.glb`);
      console.log("3D Avatar model loaded and visible!");
      
      // Load gesture libraries in background
      loadAlphabetModules();
      loadWordModules();
      loadNumberModules();

      window.addEventListener('resize', () => {
        if (state.camera && state.renderer && animationContainer) {
          const w = animationContainer.clientWidth || 360;
          const h = animationContainer.clientHeight || 280;
          state.camera.aspect = w / h;
          state.camera.updateProjectionMatrix();
          state.renderer.setSize(w, h);
        }
      });
      
      return true;
    } catch (error) {
      console.error('3D System initialization error:', error);
      return false;
    }
  }

  // Mobile Sidebar Toggle
  function initSidebarToggle() {
    const menuBtn = document.getElementById('menu-btn');
    const sidebar = document.querySelector('.sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    if (!menuBtn || !sidebar || !sidebarOverlay) return;

    const closeSidebar = () => {
      sidebar.classList.remove('open');
      sidebarOverlay.classList.remove('show');
    };

    menuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      sidebarOverlay.classList.toggle('show');
    });

    sidebarOverlay.addEventListener('click', closeSidebar);

    document.querySelectorAll('.nav-item').forEach((link) => {
      link.addEventListener('click', () => {
        if (window.innerWidth <= 768) closeSidebar();
      });
    });
  }

  async function initApp() {
    if (window.feather) feather.replace();
    initSidebarToggle();
    await init3DSystem();
    const themeToggle = document.querySelector('.theme-toggle');
    if (themeToggle) {
      themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
      });
    }
  }

  // Start the application safely
  try {
    initApp();
  } catch (err) {
    console.error("initApp top-level error:", err);
    init3DSystem();
  }
});
